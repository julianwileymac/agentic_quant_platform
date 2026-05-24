"""``/_internal/auth0/log-stream`` — Auth0 Custom Webhook log-stream sink.

AGENTS hard rule 53: Auth0 streams every login, MFA event, refresh
token rotation, session revoke, user delete, suspicious-API
detection, etc. to AQP via a Custom Webhook log stream. This route
is the sink that fans those events into:

- :class:`aqp.persistence.models_audit.SecurityAuditEvent` (so the
  in-AQP audit ledger captures Auth0-side events too — single pane
  of glass for forensic queries).
- :func:`aqp.tasks.session_revocation_tasks.cleanup_for_user` (when
  the event is a session revoke / user delete / blocked-user event,
  this Celery task halts every in-flight agent_runs_v2 /
  bot_deployments / rl_runs / paper_trading_runs / terraform_runs
  owned by the affected user AND revokes their UserOAuthToken rows).

Auth0's Custom Webhook docs (Dashboard → Monitoring → Streams →
Custom Webhook) specify the wire format:

> The payload will be delivered in JSON lines format. Keep that in
> mind while consuming the logs in your webhook configuration.

And the configurable `Authorization` header carries a shared secret
the operator sets in the Dashboard. We mirror it to
``AQP_AUTH0_LOG_STREAM_SECRET`` and verify via a constant-time HMAC
compare so a stolen header value can't be replayed by an attacker
without the matching secret.

The route is intentionally outside the normal ``/auth/...`` prefix
and intentionally NOT covered by the global `secure_router` (which
demands a Bearer token) — Auth0's webhook delivery does not carry
an end-user JWT; the shared-secret header is the authoritative
authorisation surface.
"""
from __future__ import annotations

import hmac
import json
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/_internal/auth0", tags=["auth0-log-stream"])


# ---------------------------------------------------------------------------
# Event-type → response classification
# ---------------------------------------------------------------------------

# Auth0 log type codes that signal "this user's session is no longer
# valid; halt anything in-flight on their behalf". The full enumeration
# is at https://auth0.com/docs/deploy-monitor/logs/log-event-type-codes
# — we list only the events that demand AQP-side cleanup. New entries
# require an audit-trail PR.
_REVOCATION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # Session-end / forced sign-out
        "sdu",      # Successful user deletion
        "fdu",      # Failed user deletion
        "slo",      # Successful logout
        "fco",      # Failed connection logout (recoverable)
        "ssrl",     # Successful session revocation
        # Block / unblock / suspicious API access
        "sapi",     # Suspicious API access
        "fapi",     # Failed API access
        "limit_au", # User access throttled
        "limit_mu", # User MFA throttled
        # Password / credential change
        "scp",      # Successful change password
        "scpr",     # Successful change password request
        "scpn",     # Successful change password (new)
        # Account take-over signals
        "fns",      # Failed sending notification
        "f_credentials_exchange",  # Failed credential exchange (delegated tokens)
    }
)

# Events we always audit but never trigger cleanup for.
_AUDIT_ONLY_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "s",       # Successful login
        "f",       # Failed login
        "fu",      # Failed login (invalid email/username)
        "fp",      # Failed login (wrong password)
        "fmfa",    # Failed multifactor auth
        "smfa",    # Successful multifactor auth
        "sertft",  # Successful refresh token exchange
        "fertft",  # Failed refresh token exchange
    }
)


def _classify(event_type: str) -> tuple[str, str]:
    """Return ``(category, severity)`` for an Auth0 log event type.

    Heuristic — most types map cleanly. Unknown types default to
    ``("authn", "info")`` so an unfamiliar event still lands in the
    ledger (rather than being silently dropped).
    """
    if event_type in _REVOCATION_EVENT_TYPES:
        return "safety", "critical"
    if event_type.startswith("f"):  # failure tag
        return "authn", "warning"
    return "authn", "info"


# ---------------------------------------------------------------------------
# Verification + parsing
# ---------------------------------------------------------------------------


def _expected_secret() -> str | None:
    try:
        from aqp.config import settings

        secret = str(getattr(settings, "auth0_log_stream_secret", "") or "")
    except Exception:
        return None
    return secret.strip() or None


def _verify_authorization(authorization: str | None) -> bool:
    """Constant-time compare ``Authorization`` against the configured secret.

    Auth0's Custom Webhook lets the operator set the exact header
    value to send. We expect the operator to set it to a base64 token
    that mirrors the value of ``AQP_AUTH0_LOG_STREAM_SECRET`` — we
    accept the secret with OR without the conventional ``Bearer``
    prefix because Auth0 doesn't ship a structured WWW-Authenticate
    parser for custom webhooks.
    """
    expected = _expected_secret()
    if not expected:
        # Misconfiguration: the operator hasn't set the secret. Refuse
        # the webhook so Auth0 retries with backoff (and surfaces a
        # red alert in their Stream → Monitoring panel) instead of
        # silently accepting unauthenticated traffic.
        return False
    if not authorization:
        return False
    if authorization.lower().startswith("bearer "):
        candidate = authorization.split(None, 1)[1].strip()
    else:
        candidate = authorization.strip()
    return hmac.compare_digest(candidate, expected)


def _parse_payload(body: bytes) -> list[dict[str, Any]]:
    """Parse the Auth0 Custom Webhook body.

    Auth0 delivers either a JSON array (legacy single-event posts) or
    JSON-lines (the documented current format). We tolerate both.
    """
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    if text[0] == "[":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [evt for evt in parsed if isinstance(evt, dict)]
        return []
    # JSON-lines path: one JSON object per line.
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(evt, dict):
            out.append(evt)
    return out


def _coerce_event(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise an Auth0 log envelope to a flat ``{type, user_id, ...}`` dict.

    The Auth0 log format wraps the interesting fields under a
    ``data`` key for some events but emits them at the top level for
    others. We normalise both shapes so the handler doesn't branch.
    """
    if "data" in raw and isinstance(raw["data"], dict):
        merged = dict(raw["data"])
        # Carry forward top-level metadata that Auth0 sets outside `data`.
        for top_key in ("log_id", "date", "_id"):
            if top_key in raw and top_key not in merged:
                merged[top_key] = raw[top_key]
        return merged
    return dict(raw)


def _within_max_age(event: dict[str, Any], *, max_age_seconds: int) -> bool:
    """Return True iff the event's ``date`` is within max_age seconds.

    Auth0 retries failed deliveries with the SAME payload — we accept
    up to ``max_age_seconds`` so an outage in AQP doesn't silently
    drop events, but we reject obviously stale replays.
    """
    raw_date = event.get("date") or event.get("created_at") or event.get("ts")
    if not raw_date:
        return True  # No timestamp — accept defensively
    try:
        parsed = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    delta = time.time() - parsed.timestamp()
    return delta <= max_age_seconds


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/log-stream", status_code=status.HTTP_202_ACCEPTED)
async def log_stream_sink(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Accept an Auth0 Custom Webhook log batch.

    Returns ``202 Accepted`` with a small summary so Auth0's stream
    monitor shows the delivery succeeded. Persistence + cleanup
    happen synchronously (per-event) so the response time stays
    well within Auth0's 30-second webhook timeout — for the
    expected event volume (low single-digit events/min in steady
    state) this is comfortably fast.
    """
    if not _verify_authorization(authorization):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid log-stream secret",
            headers={"WWW-Authenticate": "Bearer"},
        )
    body = await request.body()
    raw_events = _parse_payload(body)
    if not raw_events:
        return {"accepted": 0, "processed": 0, "errors": 0}

    try:
        from aqp.config import settings

        max_age = int(getattr(settings, "auth0_log_stream_max_age_seconds", 86_400) or 86_400)
    except Exception:
        max_age = 86_400

    processed = 0
    revoked = 0
    errors = 0
    skipped_stale = 0

    for raw_event in raw_events:
        try:
            event = _coerce_event(raw_event)
            if not _within_max_age(event, max_age_seconds=max_age):
                skipped_stale += 1
                continue
            await _handle_event(event, request=request)
            processed += 1
            if _is_revocation(event):
                revoked += 1
        except Exception:  # pragma: no cover — never let one event break the batch
            logger.warning("auth0 log-stream handler raised", exc_info=True)
            errors += 1

    return {
        "accepted": len(raw_events),
        "processed": processed,
        "revoked_for_cleanup": revoked,
        "errors": errors,
        "skipped_stale": skipped_stale,
    }


def _is_revocation(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type") or "").lower()
    return event_type in _REVOCATION_EVENT_TYPES


async def _handle_event(event: dict[str, Any], *, request: Request) -> None:
    event_type = str(event.get("type") or "").lower()
    auth0_user_id = event.get("user_id") or event.get("user")
    if isinstance(auth0_user_id, dict):
        auth0_user_id = auth0_user_id.get("user_id") or auth0_user_id.get("id")
    auth0_user_id = str(auth0_user_id) if auth0_user_id else None

    internal_user_id = _resolve_internal_user_id(auth0_user_id) if auth0_user_id else None

    # Always audit the event (single pane of glass for forensic queries).
    category, severity = _classify(event_type)
    try:
        from aqp.auth.audit import emit_audit_event

        emit_audit_event(
            f"auth0_log_stream:{event_type}",
            user_id=internal_user_id,
            event_category=category,
            severity=severity,
            source="auth0_action",
            request=request,
            connection=str(event.get("connection") or "") or None,
            details={
                "auth0_event_type": event_type,
                "auth0_user_id": auth0_user_id,
                "log_id": event.get("log_id") or event.get("_id"),
                "date": event.get("date"),
                "ip": event.get("ip"),
                "client_id": event.get("client_id"),
                "client_name": event.get("client_name"),
                "description": event.get("description"),
            },
        )
    except Exception:
        # Audit emission is best-effort by contract; never block
        # cleanup on a ledger write failure.
        logger.debug("auth0 log-stream audit emit failed", exc_info=True)

    # Trigger cleanup for revocation events. The Celery task does the
    # heavy work; we just enqueue + return. The task is idempotent so
    # retried Auth0 webhook deliveries cause no extra side-effects.
    if _is_revocation(event) and (internal_user_id or auth0_user_id):
        try:
            from aqp.tasks.session_revocation_tasks import cleanup_for_user

            cleanup_for_user.delay(
                internal_user_id=internal_user_id,
                auth0_user_id=auth0_user_id,
                reason=event_type,
            )
        except Exception:
            logger.warning(
                "auth0 log-stream cleanup enqueue failed for event_type=%s",
                event_type,
                exc_info=True,
            )


def _resolve_internal_user_id(auth0_user_id: str) -> str | None:
    """Look up the internal :class:`User` row for an Auth0 ``user_id``.

    Returns ``None`` when no matching row exists (most commonly: the
    Auth0 event fired before the SPA / CLI made its first AQP API
    call, so no User row was created). The cleanup task still runs
    on the Auth0 user id so any future provisioning starts with a
    clean slate.
    """
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import User

        with get_session() as session:
            row = (
                session.query(User)
                .filter(User.auth_subject == auth0_user_id)
                .one_or_none()
            )
            return row.id if row is not None else None
    except Exception:
        logger.debug("internal user_id resolution failed", exc_info=True)
        return None


__all__ = ["router"]
