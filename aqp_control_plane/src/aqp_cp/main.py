"""FastAPI application entrypoint for the AQP control plane.

Mounts the four routers (deployments, telemetry, config, secrets,
health). Auth surfaces via ``Depends(require_auth)`` on every route
except ``/manage/health``.

The active :class:`InfrastructureProvider` is selected from
``settings.provider`` and wired into the lifecycle service at startup.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aqp_cp.auth.validator import reset_validator
from aqp_cp.settings import ControlPlaneSettings, get_settings

logger = logging.getLogger("aqp_cp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "AQP control plane starting | provider=%s auth_enabled=%s issuer=%s",
        settings.provider,
        settings.auth_enabled,
        settings.auth_oidc_issuer or "<unset>",
    )
    try:
        yield
    finally:
        logger.info("AQP control plane shutting down")
        try:
            await reset_validator()
        except Exception:  # noqa: BLE001
            logger.warning("validator shutdown failed", exc_info=True)


def create_app(settings: ControlPlaneSettings | None = None) -> FastAPI:
    """FastAPI factory. Tests + the uvicorn entrypoint call this."""
    settings = settings or get_settings()
    app = FastAPI(
        title="AQP Control Plane",
        version="0.1.0",
        description=(
            "Isolated AQP control plane (AGENTS rule 45). Provider-abstracted "
            "workload runtime ops across docker_compose / kubernetes / AWS / Azure / "
            "GCP. JWT-secured /manage/* surface; resource-scoped list filtering "
            "via the https://aqp.internal/resources claim."
        ),
        contact={"name": "AQP Platform Team"},
        license_info={"name": "Proprietary"},
        lifespan=lifespan,
        openapi_url="/manage/openapi.json",
        docs_url="/manage/docs",
        redoc_url="/manage/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_routers(app)
    return app


def _register_root(app: FastAPI) -> None:
    """Register a small ``GET /`` landing handler.

    The control plane's REST surface lives under ``/manage/*``. Hitting
    the bare root used to return 404, which looked broken even though
    the service was healthy. The landing handler returns a JSON
    directory of the available surfaces so an operator browsing to
    ``http://<host>:9000/`` sees something useful immediately.
    """

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, object]:
        settings = get_settings()
        return {
            "service": "aqp-control-plane",
            "version": "0.1.0",
            "provider": settings.provider,
            "auth_enabled": settings.auth_enabled,
            "legacy_fallback_enabled": settings.legacy_fallback,
            "endpoints": {
                "health": "/manage/health",
                "openapi": "/manage/openapi.json",
                "docs": "/manage/docs",
                "redoc": "/manage/redoc",
                "deployments": "/manage/deployments",
                "telemetry_snapshot": "/manage/telemetry/snapshot",
                "config": "/manage/config/{service_id}",
                "workloads_halt": "/manage/workloads/halt",
                "workloads_halt_status": "/manage/workloads/halt/status",
                "topology": "/manage/topology",
                "streaming": "/manage/streaming/clusters",
                "observability": "/manage/observability/prometheus/query",
                "lakehouse": "/manage/lakehouse/clusters",
                "timeseries": "/manage/timeseries/questdb/status",
                "data_plane": "/manage/data-plane/services",
                # Phase 1 maturation surfaces.
                "tenants": "/manage/tenants/{tenant_id}",
                "tenant_provision": "/manage/tenants/{tenant_id}/provision",
                "builds": "/manage/builds",
                "build_logs_ws": "/manage/builds/{run_id}/logs/stream",
                "deployment_logs_ws": "/manage/deployments/{service_id}/logs/stream",
                "terraform_plan": "/manage/terraform/workspaces/{workspace_id}/plan",
                "terraform_apply": "/manage/terraform/workspaces/{workspace_id}/apply",
                "terraform_halt": "/manage/terraform/halt",
            },
        }


def _register_routers(app: FastAPI) -> None:
    """Mount the five canonical control-plane routers.

    Late import so the routers can be added in Phase 5i without making
    this module fail to load when they're not yet present.
    """
    _register_root(app)
    base = APIRouter(prefix="/manage")

    # Always-available health probe — never gated by auth.
    try:
        from aqp_cp.api.routers.health import router as health_router

        base.include_router(health_router)
    except ImportError:
        logger.info("health router not yet implemented; skipping")

    # The deployment / telemetry / config / secrets / workloads routers
    # land in Phase 5i after the provider fan-out. Each guards itself
    # with require_auth + require_scope.
    for module_name, attr in (
        ("aqp_cp.api.routers.deployments", "router"),
        ("aqp_cp.api.routers.telemetry", "router"),
        ("aqp_cp.api.routers.config", "router"),
        ("aqp_cp.api.routers.secrets", "router"),
        ("aqp_cp.api.routers.workloads", "router"),
        ("aqp_cp.api.routers.topology", "router"),
        # Phase 3 of the AQP infra-expansion plan: domain-scoped admin
        # routers for the new infra services. Read-only first; Phase 4
        # adds the mutation surfaces.
        ("aqp_cp.api.routers.streaming", "router"),
        ("aqp_cp.api.routers.observability", "router"),
        ("aqp_cp.api.routers.lakehouse", "router"),
        ("aqp_cp.api.routers.timeseries", "router"),
        ("aqp_cp.api.routers.data_plane", "router"),
        # Phase 1 of the control-plane maturation: per-tenant
        # namespace bootstrap, Kaniko in-cluster image builds, and the
        # relocated Terraform IaC runtime (rule-42 modification).
        ("aqp_cp.api.routers.tenants", "router"),
        ("aqp_cp.api.routers.builds", "router"),
        ("aqp_cp.api.routers.terraform", "router"),
        # Phase 3 §6.2 (RESTRUCTURING_PLAN.md) — cell registry CRUD
        # + state transitions + tenant placement.
        ("aqp_cp.api.routers.cells", "router"),
        # Phase 7 §10.4 — regulatory-grade evidence bundle export.
        # Returns a deterministic .tar.zst archive of audit segments +
        # transparency anchors + spec snapshots + lineage rows for a
        # given (tenant, cell, date_range) tuple.
        ("aqp_cp.api.routers.evidence_bundles", "router"),
    ):
        try:
            module = __import__(module_name, fromlist=[attr])
            base.include_router(getattr(module, attr))
        except ImportError:
            logger.info("%s not yet present; skipping", module_name)

    app.include_router(base)


# Pre-built app instance for uvicorn discovery (`uvicorn aqp_cp.main:app`).
app = create_app()


def cli() -> int:
    """Console-script entrypoint."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="aqp-control-plane")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    uvicorn.run(
        "aqp_cp.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli())


__all__ = ["app", "create_app", "cli"]
