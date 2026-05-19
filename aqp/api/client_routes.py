"""Static + legacy mounts for the unified ``aqp_client`` gateway.

When ``AQP_CLIENT_MODE=true`` the FastAPI app additionally serves:

- ``/`` -> Vite SPA from ``AQP_CLIENT_STATIC_DIR`` (default ``/app/static``)
- ``/legacy`` -> Solara ASGI app (legacy UI)
- ``/webui`` -> Legacy Next.js static bundle (rollback only)

The SPA fallback returns ``index.html`` for any unmatched route under ``/``
so client-side routing works.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

CLIENT_MODE_ENV_VAR = "AQP_CLIENT_MODE"


def is_client_mode_enabled() -> bool:
    """Return ``True`` when the gateway should mount client/SPA surfaces."""
    return os.environ.get(CLIENT_MODE_ENV_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _static_dir() -> Path:
    return Path(os.environ.get("AQP_CLIENT_STATIC_DIR", "/app/static"))


def _webui_dir() -> Path:
    return Path(os.environ.get("AQP_CLIENT_WEBUI_DIR", "/app/webui_legacy"))


def _solara_module_path() -> str:
    return os.environ.get("AQP_CLIENT_SOLARA_MODULE", "aqp.ui.app")


def mount_static(app: FastAPI) -> None:
    """Mount the Vite SPA + asset bundle on the FastAPI app."""
    static_dir = _static_dir()
    if not static_dir.exists():
        logger.warning(
            "AQP_CLIENT_MODE enabled but static dir %s does not exist; "
            "skipping SPA mount",
            static_dir,
        )
        return

    assets = static_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="vite-assets")
    if (static_dir / "_next").exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(static_dir / "_next")),
            name="next-static",
        )
    # Anything else at the root (favicon, robots, etc.) — serve from the
    # static dir without the SPA fallback so /favicon.ico returns the
    # actual icon, not index.html.
    app.mount("/_app", StaticFiles(directory=str(static_dir)), name="vite-root")


def mount_webui_rollback(app: FastAPI) -> None:
    """Mount the legacy Next.js export at ``/webui`` for rollback."""
    webui_dir = _webui_dir()
    if not webui_dir.exists():
        logger.debug(
            "AQP_CLIENT_WEBUI_DIR=%s missing; skipping /webui rollback mount",
            webui_dir,
        )
        return
    app.mount(
        "/webui",
        StaticFiles(directory=str(webui_dir), html=True),
        name="webui-legacy",
    )


def mount_solara_legacy(app: FastAPI) -> None:
    """Mount the Solara legacy UI ASGI app at ``/legacy``.

    The Solara import is optional — when ``solara`` isn't installed in the
    runtime (e.g. an arm64 image where we skip Solara to keep the image
    small) the mount is silently skipped and ``/legacy`` returns 404.
    """
    module_path = _solara_module_path()
    try:
        import importlib

        import solara.server.starlette as solara_starlette  # type: ignore[import-untyped]
    except ImportError:
        logger.info(
            "solara not installed in runtime; skipping /legacy mount "
            "(set AQP_CLIENT_ENABLE_SOLARA=false to suppress this log)"
        )
        return

    try:
        importlib.import_module(module_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "solara legacy module %s import failed: %s — /legacy will 404",
            module_path,
            exc,
        )
        return

    try:
        legacy_app = solara_starlette.ServerStarlette(app_name=module_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("solara ServerStarlette init failed: %s", exc)
        return

    app.mount("/legacy", legacy_app, name="solara-legacy")


def register_spa_fallback(app: FastAPI) -> None:
    """Add a catch-all GET route that returns ``index.html`` for SPA routes.

    MUST be added AFTER every other router so it's the last-resort
    handler. FastAPI matches in registration order.
    """
    index_path = _static_dir() / "index.html"
    if not index_path.exists():
        logger.warning(
            "SPA fallback enabled but index.html missing at %s — "
            "client routes will return 404",
            index_path,
        )
        return

    @app.get("/{full_path:path}", include_in_schema=False, name="spa_fallback")
    async def serve_spa(full_path: str, request: Request) -> Response:
        # Don't serve the SPA shell for API-style paths — those should
        # 404 cleanly so the client knows something's wrong.
        if full_path.startswith(
            ("api/", "ml/", "mcp/", "manage/", "ws/", "legacy/", "webui/", "static/", "assets/", "_app/")
        ):
            raise HTTPException(status_code=404)
        # Health endpoint is registered earlier; fallback should not
        # shadow it. FastAPI's route matcher handles that ordering as
        # long as register_spa_fallback() runs last.
        return FileResponse(str(index_path))


def install_client_surfaces(app: FastAPI) -> None:
    """One-shot installer — call from ``aqp.api.main`` after router setup.

    Mounts static + legacy + Solara, builds the HTTP + WS proxy routers,
    and registers the SPA fallback last. No-op when client mode is off.
    """
    if not is_client_mode_enabled():
        return

    from aqp.api.proxy import build_proxy_router, close_http_client
    from aqp.api.ws_proxy import build_websocket_proxy_router

    mount_static(app)
    mount_webui_rollback(app)
    mount_solara_legacy(app)

    app.include_router(build_proxy_router())
    app.include_router(build_websocket_proxy_router())

    # SPA fallback ABSOLUTELY LAST.
    register_spa_fallback(app)

    @app.on_event("shutdown")
    async def _close_proxy_http_client() -> None:
        await close_http_client()


__all__ = [
    "CLIENT_MODE_ENV_VAR",
    "install_client_surfaces",
    "is_client_mode_enabled",
]
