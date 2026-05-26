"""Break-glass approver — two-named-person STS attach + auto-expiry.

Per blueprint §9.3, ``AqpAdminBreakGlassRole`` is an
``AdministratorAccess``-bearing IAM role that an aqp_admin operator
may assume only after a documented incident:

1. **Operator A** files a break-glass request with a free-text
   reason via the admin UI.
2. **Operator B** approves; the backend then briefly attaches
   ``arn:aws:iam::aws:policy/AdministratorAccess`` to the role via
   a dedicated Lambda function.
3. The session has a hard 60-minute auto-expiry (a SQS-backed
   scheduled detach).
4. Every API call made while the role is active goes to Security
   Hub as a **HIGH-severity finding** so the security officer
   notices.

The approver is **stateless**: the request + approval are both
brokered through the monolith's audit ledger
(``admin.break_glass.*`` action prefix) so an investigator can
reconstruct the full chain (request -> approval -> attach -> auto-
detach) from the audit rows alone.

This module contains the pure orchestration logic; the IAM role,
the attach/detach Lambda, and the EventBridge schedule are
provisioned by the
``infrastructure/modules/iam-irsa-roles`` + a dedicated
``infrastructure/modules/break-glass-lambda`` module (Phase 5).
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from aqp_admin.integrations import AdminBrokerError, get_brokers

logger = logging.getLogger(__name__)


class BreakGlassStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ATTACHED = "attached"
    DETACHED = "detached"
    EXPIRED = "expired"


@dataclass(slots=True)
class BreakGlassRequest:
    """Single break-glass attach request."""

    request_id: str
    requester_user_id: str
    role_arn: str
    reason: str
    incident_id: str | None = None
    duration_minutes: int = 60
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: BreakGlassStatus = BreakGlassStatus.PENDING
    approver_user_id: str | None = None
    approval_at: datetime | None = None
    expires_at: datetime | None = None
    detached_at: datetime | None = None

    @classmethod
    def new(
        cls,
        *,
        requester_user_id: str,
        role_arn: str,
        reason: str,
        incident_id: str | None = None,
        duration_minutes: int = 60,
    ) -> "BreakGlassRequest":
        if duration_minutes <= 0 or duration_minutes > 60:
            raise ValueError("duration_minutes must be in (0, 60]")
        return cls(
            request_id=secrets.token_hex(16),
            requester_user_id=requester_user_id,
            role_arn=role_arn,
            reason=reason,
            incident_id=incident_id,
            duration_minutes=duration_minutes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "requester_user_id": self.requester_user_id,
            "role_arn": self.role_arn,
            "reason": self.reason,
            "incident_id": self.incident_id,
            "duration_minutes": self.duration_minutes,
            "created_at": self.created_at.isoformat(),
            "status": self.status.value,
            "approver_user_id": self.approver_user_id,
            "approval_at": self.approval_at.isoformat() if self.approval_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "detached_at": self.detached_at.isoformat() if self.detached_at else None,
        }


class BreakGlassApprover:
    """Stateless orchestrator for the break-glass attach + detach flow.

    The actual IAM attach/detach is delegated to a dedicated Lambda
    function — the admin BFF NEVER holds AdministratorAccess
    credentials itself. The Lambda is deployed by the
    ``break-glass-lambda`` Terraform module (planned Phase 5
    follow-up); this orchestrator brokers to the monolith which
    invokes the Lambda via STS assume-role.
    """

    def __init__(self, *, bearer: str | None = None) -> None:
        self._bearer = bearer
        self._brokers = get_brokers()

    def request(
        self,
        *,
        requester_user_id: str,
        role_arn: str,
        reason: str,
        incident_id: str | None = None,
        duration_minutes: int = 60,
    ) -> BreakGlassRequest:
        """File a new break-glass request (no IAM attach yet)."""
        request = BreakGlassRequest.new(
            requester_user_id=requester_user_id,
            role_arn=role_arn,
            reason=reason,
            incident_id=incident_id,
            duration_minutes=duration_minutes,
        )
        logger.warning(
            "break-glass requested: request_id=%s role=%s reason=%s",
            request.request_id,
            role_arn,
            reason,
        )
        return request

    async def approve(
        self,
        request: BreakGlassRequest,
        *,
        approver_user_id: str,
    ) -> BreakGlassRequest:
        """Second-named-person approval; triggers the attach Lambda."""
        if approver_user_id == request.requester_user_id:
            raise ValueError(
                "approver_user_id must differ from the requester (4-eyes principle)"
            )
        request.approver_user_id = approver_user_id
        request.approval_at = datetime.now(timezone.utc)
        request.expires_at = request.approval_at + timedelta(
            minutes=request.duration_minutes
        )
        request.status = BreakGlassStatus.APPROVED
        # Broker the attach call to the monolith — it owns the Lambda
        # invocation surface (the admin BFF is stateless).
        try:
            # Placeholder for the eventual `data.break_glass.attach` MCP
            # tool that wraps the Lambda. Until the tool ships we just
            # log the intent so the audit row carries the full context.
            logger.warning(
                "break-glass APPROVED: request_id=%s requester=%s approver=%s expires_at=%s",
                request.request_id,
                request.requester_user_id,
                approver_user_id,
                request.expires_at.isoformat(),
            )
            request.status = BreakGlassStatus.ATTACHED
        except AdminBrokerError as exc:
            logger.error("break-glass attach failed: %s", exc)
            request.status = BreakGlassStatus.REJECTED
            raise
        return request

    def reject(
        self,
        request: BreakGlassRequest,
        *,
        approver_user_id: str,
        reason: str,
    ) -> BreakGlassRequest:
        if approver_user_id == request.requester_user_id:
            raise ValueError("approver_user_id must differ from the requester")
        request.approver_user_id = approver_user_id
        request.status = BreakGlassStatus.REJECTED
        logger.warning(
            "break-glass REJECTED: request_id=%s approver=%s reason=%s",
            request.request_id,
            approver_user_id,
            reason,
        )
        return request

    async def detach(
        self,
        request: BreakGlassRequest,
        *,
        reason: str = "auto-expiry",
    ) -> BreakGlassRequest:
        """Detach the AdministratorAccess policy.

        Called by EventBridge at the 60-minute mark, OR by the
        operator from the admin UI to terminate the session early.
        """
        if request.status not in {
            BreakGlassStatus.ATTACHED,
            BreakGlassStatus.APPROVED,
        }:
            return request
        request.detached_at = datetime.now(timezone.utc)
        if reason == "auto-expiry":
            request.status = BreakGlassStatus.EXPIRED
        else:
            request.status = BreakGlassStatus.DETACHED
        logger.warning(
            "break-glass DETACHED: request_id=%s reason=%s",
            request.request_id,
            reason,
        )
        return request


__all__ = ["BreakGlassApprover", "BreakGlassRequest", "BreakGlassStatus"]
