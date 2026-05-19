"""Provider lookup + audit-wrapped orchestration of workload ops."""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from fastapi import HTTPException, status

from aqp_cp.auth.deps import AuthenticatedUser
from aqp_cp.models import (
    ConfigMapPatch,
    DeploymentSpec,
    DeploymentStatus,
    ServiceConfig,
    WorkloadAction,
    WorkloadRun,
    WorkloadRunStatus,
)
from aqp_cp.providers import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
    bootstrap,
    get_provider_registry,
)
from aqp_cp.services import audit
from aqp_cp.settings import get_settings

logger = logging.getLogger(__name__)


def get_active_provider(alias: str | None = None) -> InfrastructureProvider:
    """Return the configured :class:`InfrastructureProvider` instance.

    Defaults to ``settings.provider``; ``alias`` lets the operator
    override per-request (rare — primarily for the admin API).
    """
    bootstrap()  # idempotent
    settings = get_settings()
    chosen = alias or settings.provider
    try:
        return get_provider_registry().get_or_create(chosen)
    except InfrastructureProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": exc.code, "error_description": str(exc)},
        ) from exc


async def execute_with_audit(
    *,
    action: WorkloadAction,
    target: str,
    user: AuthenticatedUser,
    payload: dict[str, Any] | None,
    fn: Callable[[], Awaitable[Any]],
    request_id: str | None = None,
    provider_alias: str | None = None,
) -> tuple[WorkloadRun, Any]:
    """Wrap a provider call with audit start + finish + structured errors."""
    settings = get_settings()
    prov_alias = provider_alias or settings.provider
    run = audit.start_run(
        action=action,
        provider=prov_alias,
        target=target,
        user_id=user.sub,
        request_id=request_id,
        org_id=user.org_id,
        workspace_id=user.workspace_id,
        payload=payload,
    )
    try:
        result = await fn()
    except InfrastructureProviderUnavailable as exc:
        audit.finish_run(run, status=WorkloadRunStatus.FAILED, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": exc.code,
                "error_description": str(exc),
                "provider": exc.provider,
                "details": exc.details,
            },
        ) from exc
    except InfrastructureProviderError as exc:
        audit.finish_run(run, status=WorkloadRunStatus.FAILED, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": exc.code,
                "error_description": str(exc),
                "provider": exc.provider,
                "details": exc.details,
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        audit.finish_run(run, status=WorkloadRunStatus.FAILED, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal", "error_description": str(exc)},
        ) from exc

    # Normalise result -> dict for the audit row.
    if hasattr(result, "model_dump"):
        result_dict = result.model_dump(mode="json")
    elif isinstance(result, list):
        result_dict = {"count": len(result)}
    elif isinstance(result, dict):
        result_dict = result
    else:
        result_dict = {"value": str(result)}
    audit.finish_run(run, status=WorkloadRunStatus.SUCCEEDED, result=result_dict)
    return run, result


__all__ = ["execute_with_audit", "get_active_provider"]
