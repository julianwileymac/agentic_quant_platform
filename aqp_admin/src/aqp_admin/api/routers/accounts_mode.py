# ruff: noqa: B008, ARG001
"""``/admin/accounts/mode`` — single- vs multi-account mode switcher.

Implements the Phase 4 state machine from the overhaul blueprint
(§4.4):

::

    UNCONFIGURED
        |
        v
    SINGLE_ACCOUNT  -- enable_multi_account -->  MULTI_ACCOUNT_DETECTING
                                                       |
                                                       v
                                              MULTI_ACCOUNT_READY
                                                       |
                                                drift detected
                                                       v
                                              MULTI_ACCOUNT_DEGRADED

The detector inspects:

- AWS STS ``GetCallerIdentity`` (does the runtime have AWS credentials?)
- AWS Organizations ``DescribeOrganization`` (is the account in an Org?)
- AWS Control Tower ``ListLandingZones`` (is the Org Control-Tower-enrolled?)

A persisted operator override (``account_mode`` row in the monolith
admin DB) wins over the live detection so an operator can pin the
mode during a maintenance window without the detector flapping.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.deps.stepup import require_admin_step_up
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/accounts/mode", tags=["accounts-mode"])
logger = logging.getLogger(__name__)


class AccountMode(str, Enum):
    UNCONFIGURED = "unconfigured"
    SINGLE_ACCOUNT = "single-account"
    MULTI_ACCOUNT_DETECTING = "multi-account-detecting"
    MULTI_ACCOUNT_READY = "multi-account-ready"
    MULTI_ACCOUNT_DEGRADED = "multi-account-degraded"


_VALID_TRANSITIONS = {
    AccountMode.UNCONFIGURED: {
        AccountMode.SINGLE_ACCOUNT,
        AccountMode.MULTI_ACCOUNT_DETECTING,
    },
    AccountMode.SINGLE_ACCOUNT: {
        AccountMode.MULTI_ACCOUNT_DETECTING,
    },
    AccountMode.MULTI_ACCOUNT_DETECTING: {
        AccountMode.MULTI_ACCOUNT_READY,
        AccountMode.MULTI_ACCOUNT_DEGRADED,
        AccountMode.SINGLE_ACCOUNT,  # rollback during enable wizard
    },
    AccountMode.MULTI_ACCOUNT_READY: {
        AccountMode.MULTI_ACCOUNT_DEGRADED,
    },
    AccountMode.MULTI_ACCOUNT_DEGRADED: {
        AccountMode.MULTI_ACCOUNT_READY,
    },
}


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


def _detect_mode_via_aws() -> tuple[AccountMode, dict[str, Any]]:
    """Inspect the live AWS environment for an Org / Control Tower setup.

    Returns ``(mode, evidence)`` where ``evidence`` is a JSON-safe
    dict suitable for inclusion in the audit row. No secrets land
    in evidence — only account ids + ARNs + boolean flags.
    """
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError:
        return AccountMode.UNCONFIGURED, {"reason": "boto3 not installed"}

    sts = boto3.client("sts")
    try:
        ident = sts.get_caller_identity()
    except Exception as exc:  # noqa: BLE001
        logger.debug("STS get_caller_identity failed: %s", exc)
        return AccountMode.UNCONFIGURED, {"reason": "no_aws_credentials"}

    evidence: dict[str, Any] = {
        "aws_account_id": ident.get("Account"),
        "aws_caller_arn": ident.get("Arn"),
    }

    try:
        orgs = boto3.client("organizations")
        org = orgs.describe_organization()["Organization"]
        evidence["org_id"] = org.get("Id")
        evidence["org_master_account_id"] = org.get("MasterAccountId")
        if ident.get("Account") != org.get("MasterAccountId"):
            evidence["caller_role"] = "member"
            return AccountMode.MULTI_ACCOUNT_READY, evidence
        evidence["caller_role"] = "master"
        try:
            ct = boto3.client("controltower")
            ct.list_landing_zones()
            evidence["control_tower"] = True
            return AccountMode.MULTI_ACCOUNT_READY, evidence
        except Exception as exc:  # noqa: BLE001
            evidence["control_tower"] = False
            evidence["control_tower_error"] = str(exc)[:240]
            return AccountMode.MULTI_ACCOUNT_DEGRADED, evidence
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "AWSOrganizationsNotInUseException" in message:
            return AccountMode.SINGLE_ACCOUNT, evidence
        evidence["org_error"] = message[:240]
        return AccountMode.SINGLE_ACCOUNT, evidence


class EnableMultiAccountBody(BaseModel):
    """Request body for the multi-account enable wizard."""

    landing_zone_workspace_id: str = Field(
        ...,
        description=(
            "TerraformWorkspace id for the landing-zone stack. The "
            "wizard runs `terraform apply` against this workspace via "
            "the existing TerraformRuntime path (rule 42)."
        ),
    )
    approver_user_id: str = Field(
        ...,
        description="Second AQP admin who approves the promotion (4-eyes).",
    )
    reason: str = Field(..., min_length=10, max_length=400)


class PinModeBody(BaseModel):
    mode: AccountMode
    reason: str = Field(..., min_length=4, max_length=200)


@router.get("", summary="Read the current account mode + live detection.")
async def read_mode(
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Return the active account mode plus a fresh detector probe.

    Response shape::

        {
          "active_mode": "single-account",
          "operator_pinned": false,
          "live_detection": {"mode": "single-account", "evidence": {...}}
        }

    The active mode is whichever the operator has pinned (if any),
    falling back to the live detection. The UI surfaces both so an
    operator can see when their pin is out-of-sync with reality.
    """
    detected_mode, evidence = _detect_mode_via_aws()
    try:
        persisted = await get_brokers().monolith.get_account_mode(
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        # If the persistence layer is unavailable, surface the live
        # detection so the operator can still inspect their AWS env.
        logger.warning("account_mode broker read failed: %s", exc)
        persisted = {"mode": None, "operator_pinned": False, "updated_at": None}

    pinned = bool(persisted.get("operator_pinned"))
    pinned_mode = persisted.get("mode")
    active = AccountMode(pinned_mode) if pinned and pinned_mode else detected_mode

    return {
        "active_mode": active.value,
        "operator_pinned": pinned,
        "operator_pin": persisted,
        "live_detection": {
            "mode": detected_mode.value,
            "evidence": evidence,
        },
    }


@router.post(
    "/pin",
    summary="Pin the active account mode (override the detector).",
)
async def pin_mode(
    body: PinModeBody,
    user: AdminUser = Depends(
        require_admin_step_up("platform:admin", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.accounts_mode.pin")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Pin the account mode; the detector is bypassed until cleared."""
    audit.target = body.mode.value
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().monolith.set_account_mode(
            mode=body.mode.value,
            reason=body.reason,
            operator_pinned=True,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"mode": body.mode.value, "operator_pinned": True})
    return {"result": result, "audit_run_id": audit.run_id}


@router.delete(
    "/pin",
    summary="Clear the operator pin and fall back to live detection.",
)
async def clear_pin(
    reason: str,
    user: AdminUser = Depends(
        require_admin_step_up("platform:admin", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.accounts_mode.unpin")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.start(payload={"reason": reason})
    try:
        result = await get_brokers().monolith.clear_account_mode_pin(
            reason=reason,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"cleared": True})
    return {"result": result, "audit_run_id": audit.run_id}


@router.post(
    "/enable-multi-account",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Promote SINGLE_ACCOUNT -> MULTI_ACCOUNT via Terraform.",
)
async def enable_multi_account(
    body: EnableMultiAccountBody,
    user: AdminUser = Depends(
        require_admin_step_up("terraform:apply", "platform:admin", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(
        audit_context_dep("admin.accounts_mode.enable_multi_account"),
    ),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Trigger the landing-zone Terraform apply.

    Brokers to the existing TerraformRuntime path (rule 42); the
    runtime persists ``terraform_runs`` rows + emits the
    canonical progress frame. The 4-eyes approval is enforced
    upstream by ``TerraformRuntime`` when ``approver_user_id !=
    sub``.
    """
    if user.sub == body.approver_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "self_approval_rejected",
                "error_description": (
                    "approver_user_id must differ from the requesting user "
                    "(4-eyes principle)"
                ),
            },
        )

    # Step 1 — pin the mode to MULTI_ACCOUNT_DETECTING so the UI shows
    # "in progress" while the Terraform apply runs.
    audit.target = body.landing_zone_workspace_id
    audit.start(payload=body.model_dump())
    try:
        await get_brokers().monolith.set_account_mode(
            mode=AccountMode.MULTI_ACCOUNT_DETECTING.value,
            reason=f"enable-multi-account: {body.reason}",
            operator_pinned=True,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)

    # Step 2 — broker the Terraform apply through the CP. The CP-side
    # TerraformRuntime is the only sanctioned executor (rule 42).
    try:
        result = await get_brokers().control_plane.terraform_run(
            workspace_id=body.landing_zone_workspace_id,
            action="apply",
            body={
                "approver_user_id": body.approver_user_id,
                "experiment_id": None,
                "test_id": None,
                "extra_args": [],
                "reason": body.reason,
            },
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)

    audit.succeed(
        {
            "terraform_run_id": result.get("run_id"),
            "workspace_id": body.landing_zone_workspace_id,
        }
    )
    return {
        "result": result,
        "audit_run_id": audit.run_id,
        "next_step": (
            "poll GET /admin/terraform/runs/{run_id} until status='succeeded', "
            "then GET /admin/accounts/mode to confirm MULTI_ACCOUNT_READY"
        ),
    }


__all__ = ["AccountMode", "router"]
