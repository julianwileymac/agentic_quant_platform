"""FastAPI entrypoint for the internal admin surface.

Mounts the canonical admin routers behind Entra-primary bearer
validation. Health is intentionally public; everything else routes
through :func:`require_admin` (Entra) with optional Auth0 fallback.

Audit-first wiring: every mutating route accepts an
:class:`AuditContext` ``Depends(...)`` so the JSONL / HTTP sink
writes a ``status=pending`` row BEFORE the action and the matching
``status=succeeded|failed`` row AFTER.

This module exposes a ``cli()`` console-script entry-point so the
package can be launched with ``aqp-admin-api`` after ``pip install``.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aqp_admin.audit.sink import build_default_audit_sink, reset_audit_sink
from aqp_admin.deps.identity import reset_admin_validator
from aqp_admin.settings import AdminSettings, get_settings

logger = logging.getLogger("aqp_admin")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    settings = get_settings()
    logger.info(
        "aqp_admin starting | api=%s control_plane=%s auth_enabled=%s audit_sink=%s",
        settings.api_url,
        settings.control_plane_url,
        settings.auth_enabled,
        settings.audit_sink,
    )
    # Warm the audit sink so the first request doesn't pay the I/O cost.
    try:
        build_default_audit_sink(settings)
    except Exception:  # noqa: BLE001
        logger.warning("audit sink warmup failed", exc_info=True)
    try:
        yield
    finally:
        logger.info("aqp_admin stopping")
        try:
            await reset_admin_validator()
        except Exception:  # noqa: BLE001
            logger.debug("validator shutdown failed", exc_info=True)
        reset_audit_sink()


def create_app(settings: AdminSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="AQP Admin",
        description=(
            "Internal admin surface for AQP managed services + company "
            "accounts. Entra-primary bearer validation, audit-first "
            "mutations brokered to aqp_control_plane and the AQP monolith."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _register_root(app, settings)
    _register_routers(app)
    return app


def _register_root(app: FastAPI, settings: AdminSettings) -> None:
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, object]:
        return {
            "service": "aqp-admin",
            "version": "0.1.0",
            "auth_enabled": settings.auth_enabled,
            "auth_provider": settings.auth_provider,
            "endpoints": {
                "health": "/admin/health",
                "openapi": "/openapi.json",
                "docs": "/docs",
                "accounts": "/admin/accounts/organizations",
                "services": "/admin/services",
                "settings": "/admin/settings/framework",
                "tenants": "/admin/tenants",
                "halt_all": "/admin/halt/all",
                "audit_runs": "/admin/audit/runs",
            },
        }


def _register_routers(app: FastAPI) -> None:
    """Mount the canonical admin routers (best-effort imports).

    Routers land in Phase 1 (admin-real-services + admin-ui-kill-switch).
    Each guards itself with ``require_admin`` / ``require_admin_scope``.
    """
    # health first — never gated.
    from aqp_admin.api.routers import health

    app.include_router(health.router)

    for module_name, attr in (
        ("aqp_admin.api.routers.accounts", "router"),
        ("aqp_admin.api.routers.services", "router"),
        ("aqp_admin.api.routers.settings", "router"),
        ("aqp_admin.api.routers.tenants", "router"),
        ("aqp_admin.api.routers.halt", "router"),
        ("aqp_admin.api.routers.audit", "router"),
        ("aqp_admin.api.routers.builds", "router"),
        ("aqp_admin.api.routers.runbooks", "router"),
        ("aqp_admin.api.routers.metrics", "router"),
    ):
        try:
            module = __import__(module_name, fromlist=[attr])
            app.include_router(getattr(module, attr))
        except ImportError:
            logger.info("admin router %s not yet present; skipping", module_name)


app = create_app()


def cli() -> None:
    """Console-script entrypoint registered in pyproject.toml."""
    uvicorn.run("aqp_admin.main:app", host="0.0.0.0", port=8900, reload=False)  # noqa: S104


if __name__ == "__main__":
    cli()


__all__ = ["app", "cli", "create_app"]
