"""Security audit event emit helper.

One canonical entry point for writing :class:`SecurityAuditEvent` rows.
Used by every login, /me/* mutation, password change, MFA enroll/remove,
session revoke, role change, kill-switch flip, and Auth0 Action sync.

Hard rules:

- ``logger = logging.getLogger(__name__)`` at module top (rule 9).
- ``from __future__ import annotations`` at top.
- Type hints on every public function (rule 8).
- ``emit_audit_event`` MUST NEVER raise from a caller's perspective.
- Gated by ``settings.auth_audit_enabled`` (default True).
- Resolves IP / user_agent from a FastAPI ``Request`` when provided.
- Resolves OTEL trace id from the active span when available.
- Uses ``get_session`` context manager from ``aqp.persistence.db``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)

EventCategory = Literal["authn", "authz", "account", "tenancy", "safety"]
Severity = Literal["info", "warning", "critical"]
Source = Literal["api", "auth0_action", "watchdog", "celery", "cli"]


def emit_audit_event(
    event_type: str,
    *,
    user_id: str | None = None,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    actor_user_id: str | None = None,
    event_category: EventCategory = "authn",
    severity: Severity = "info",
    source: Source = "api",
    connection: str | None = None,
    request: Request | None = None,
    details: dict[str, Any] | None = None,
    on_behalf_of_user_id: str | None = None,
    agent_subject: str | None = None,
    delegation_profile: str | None = None,
) -> None:
    """Write a SecurityAuditEvent row, swallowing any failures.

    Called from login / /me/* mutation / kill-switch / Auth0 Action sync.
    Always returns ``None`` and never raises.

    Delegation chain (RFC 8693 / AGENTS hard rule 54):

    - When an autonomous agent acts on behalf of a human via a
      delegated token (``act`` claim present on the access token),
      callers should pass ``user_id=<human user_id>``,
      ``actor_user_id=<human user_id>``, ``agent_subject="agent|<client_id>"``,
      ``on_behalf_of_user_id=<human user_id>``, and optionally
      ``delegation_profile="aqp-agent-delegation"``.
    - The FK-constrained ``user_id`` / ``actor_user_id`` columns stay
      pointed at the human (otherwise the FK would reject the row),
      while the agent identity + profile name land in ``details`` so
      the audit query surface can filter by either dimension.
    - When ``on_behalf_of_user_id`` differs from ``actor_user_id`` the
      ``details["delegation"]`` block is set with the full chain so
      downstream SIEM / dashboards see who-on-behalf-of-whom.
    """
    try:
        if not _audit_enabled():
            return

        # Lazy imports keep auth flows resilient before audit migration lands.
        from aqp.persistence.db import get_session
        from aqp.persistence.models_audit import SecurityAuditEvent

        merged_details: dict[str, Any] = dict(details or {})
        if agent_subject or on_behalf_of_user_id or delegation_profile:
            merged_details.setdefault("delegation", {}).update(
                {
                    "agent_subject": agent_subject,
                    "on_behalf_of_user_id": on_behalf_of_user_id,
                    "profile": delegation_profile,
                }
            )

        row = SecurityAuditEvent(
            user_id=user_id,
            organization_id=organization_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id or user_id,
            event_type=event_type,
            event_category=event_category,
            severity=severity,
            source=source,
            connection=connection,
            request_id=_resolve_trace_id(),
            ip=_resolve_ip(request),
            user_agent=_resolve_user_agent(request),
            details=merged_details,
        )
        with get_session() as session:
            session.add(row)
            session.flush()
    except Exception:
        logger.warning(
            "audit.emit_failed event_type=%r user_id=%r",
            event_type,
            user_id,
            exc_info=True,
        )


def _resolve_ip(request: Request | None) -> str | None:
    """Return the best-effort client IP from a FastAPI Request."""
    if request is None:
        return None
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        first = xff.split(",", 1)[0].strip()
        if first:
            return first
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        value = x_real_ip.strip()
        if value:
            return value
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    if isinstance(host, str):
        value = host.strip()
        if value:
            return value
    return None


def _resolve_user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    user_agent = request.headers.get("User-Agent")
    if not user_agent:
        return None
    value = user_agent.strip()
    return value or None


def _resolve_trace_id() -> str | None:
    """Return the active OTEL trace id as a hex string, or ``None``."""
    try:
        from opentelemetry import trace as _otel_trace

        span = _otel_trace.get_current_span()
        if span is None:
            return None
        ctx = span.get_span_context()
        if not ctx:
            return None
        is_valid = getattr(ctx, "is_valid", False)
        if callable(is_valid):
            is_valid = is_valid()
        if not is_valid:
            return None
        trace_id = int(getattr(ctx, "trace_id", 0))
        if trace_id <= 0:
            return None
        return format(trace_id, "032x")
    except Exception:
        return None


def _audit_enabled() -> bool:
    try:
        from aqp.config import settings

        return bool(getattr(settings, "auth_audit_enabled", True))
    except Exception:
        return True


__all__ = ["emit_audit_event"]
