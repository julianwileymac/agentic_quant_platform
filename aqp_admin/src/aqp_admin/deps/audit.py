"""Audit dependencies — per-request :class:`AuditContext` + sink access.

Routes accept :class:`AuditContext` as a ``Depends(...)`` so they can
call :meth:`AuditContext.start` BEFORE the action and
:meth:`AuditContext.succeed` / :meth:`AuditContext.fail` AFTER. The
context is bound to the active admin user + request id so the audit
row carries the actor identity end-to-end.

Example::

    @router.post("/admin/tenants")
    async def create_tenant(
        body: CreateTenantBody,
        user: AdminUser = Depends(require_admin),
        audit: AuditContext = Depends(audit_context_dep("admin.tenants.create")),
    ) -> ResponseEnvelope[Tenant]:
        audit.target = body.tenant_id
        audit.start(payload=body.model_dump())
        try:
            tenant = await tenant_service.create(body, user=user)
            audit.succeed({"tenant_id": tenant.id})
            return ResponseEnvelope(status="ok", data=tenant)
        except Exception as exc:
            audit.fail(str(exc))
            raise
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from fastapi import Depends, Header, Request

from aqp_admin.audit.sink import (
    AdminAuditEvent,
    AdminAuditSink,
    finalise_event,
    get_audit_sink,
    new_event,
)
from aqp_admin.deps.identity import AdminUser, require_admin


@dataclass(slots=True)
class AuditContext:
    """Per-request audit handle bound to the active admin user."""

    action: str
    actor_sub: str
    org_id: str | None = None
    workspace_id: str | None = None
    request_id: str | None = None
    target: str = ""
    _event: AdminAuditEvent | None = None
    _sink: AdminAuditSink | None = None

    def bind_sink(self, sink: AdminAuditSink) -> None:
        self._sink = sink

    def start(self, *, payload: dict[str, Any] | None = None, target: str | None = None) -> AdminAuditEvent:
        """Write the ``status=pending`` row BEFORE dispatching the action."""
        if target is not None:
            self.target = target
        self._event = new_event(
            action=self.action,
            target=self.target or "<unknown>",
            actor_sub=self.actor_sub,
            org_id=self.org_id,
            workspace_id=self.workspace_id,
            request_id=self.request_id,
            payload=payload,
        )
        if self._sink is not None:
            self._sink.start(self._event)
        return self._event

    def succeed(self, result: dict[str, Any] | None = None) -> AdminAuditEvent | None:
        if self._event is None:
            return None
        finalised = finalise_event(self._event, status="succeeded", result=result)
        if self._sink is not None:
            self._sink.finish(finalised)
        return finalised

    def fail(self, error: str) -> AdminAuditEvent | None:
        if self._event is None:
            return None
        finalised = finalise_event(self._event, status="failed", error=error)
        if self._sink is not None:
            self._sink.finish(finalised)
        return finalised

    @property
    def run_id(self) -> str | None:
        return self._event.run_id if self._event is not None else None


def audit_context_dep(action: str) -> Callable[..., AuditContext]:
    """Build a :class:`AuditContext` dependency for ``action``.

    The returned dep wires the active admin user + request id +
    audit sink into the context. Routes only need to call
    :meth:`AuditContext.start` once they know the target payload.
    """

    def _dep(
        request: Request,
        user: AdminUser = Depends(require_admin),
        x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    ) -> AuditContext:
        ctx = AuditContext(
            action=action,
            actor_sub=user.sub,
            org_id=user.org_id,
            workspace_id=user.workspace_id,
            request_id=x_request_id,
        )
        ctx.bind_sink(get_audit_sink())
        request.state.aqp_admin_audit = ctx
        return ctx

    return _dep


__all__ = [
    "AuditContext",
    "audit_context_dep",
    "get_audit_sink",
]
