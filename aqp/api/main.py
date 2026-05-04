"""FastAPI gateway — the synchronous entry point for the UI and external clients.

This module also mounts the Dash visualization engine at ``/dash`` so the
whole platform is reachable from a single port.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aqp.api.routes import (
    agent_specs,
    agentic,
    agents,
    alpha_vantage,
    analysis_agents,
    airbyte,
    auth,
    backtest,
    bots as bots_routes,
    brokers,
    cfpb,
    chat,
    data,
    data_control,
    data_pipelines,
    datalinks,
    datasets,
    dataset_presets,
    dbt,
    entities,
    factors,
    fda,
    feature_catalog,
    feature_sets,
    fred,
    gdelt,
    health,
    identifiers,
    market_data_live,
    memory,
    metadata_catalog,
    ml,
    monitoring,
    paper,
    portfolio,
    rag,
    registry,
    research_agents,
    rl,
    sec,
    security,
    selection_agents,
    sinks as sinks_routes,
    sources,
    strategies,
    trader_agents,
    uspto,
    visualizations,
)
# Data layer expansion: Kafka/Flink/producers admin + cluster proxy
from aqp.api.routes import (  # noqa: E402
    cluster_mgmt as cluster_mgmt_routes,
    dataset_loading_agent as dataset_loading_agent_routes,
    flink as flink_routes,
    kafka as kafka_routes,
    producers as producers_routes,
    streaming_links as streaming_links_routes,
)
# Data fabric expansion (Phase 5/6/7) — the new engine, entity registry,
# Dagster proxy, DataHub sync routers. Imported separately so a hard
# import error here doesn't take down the existing routes.
from aqp.api.routes import (  # noqa: E402
    compute as compute_routes,
    dagster as dagster_routes,
    datahub as datahub_routes,
    engine as engine_routes,
    entity_registry as entity_registry_routes,
    fetchers as fetcher_routes,
    service_manager as service_manager_routes,
)
# Tenancy (multi-tenant resource ownership refactor)
from aqp.api.routes import (  # noqa: E402
    configs as configs_routes,
    labs as labs_routes,
    orgs as orgs_routes,
    projects as projects_routes,
    teams as teams_routes,
    users as users_routes,
    workspaces as workspaces_routes,
)
from aqp.config import settings
from aqp.observability import (
    configure_tracing,
    instrument_fastapi,
    shutdown_tracing,
)
from aqp.observability.tracing import instrument_httpx, instrument_redis

logger = logging.getLogger(__name__)


configure_tracing(service_name=f"{settings.otel_service_name}-api")
instrument_httpx()
instrument_redis()


def _maybe_run_iceberg_bootstrap() -> None:
    """Run the Polaris/Iceberg bootstrap manager when ``AQP_ICEBERG_AUTO_BOOTSTRAP`` is enabled.

    Failures are logged but never block startup so the API can still
    expose the manual ``/service-manager/iceberg/bootstrap`` endpoint.
    """
    if not settings.iceberg_auto_bootstrap:
        return
    try:
        from aqp.services.iceberg_bootstrap import IcebergBootstrapManager

        with IcebergBootstrapManager() as manager:
            report = manager.bootstrap()
        logger.info(
            "Iceberg auto-bootstrap finished: success=%s steps=%d duration=%.2fs",
            report.success,
            len(report.steps),
            report.duration_seconds,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Iceberg auto-bootstrap failed; manual /service-manager/iceberg/bootstrap available")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AQP API starting | env=%s", settings.env)
    _maybe_run_iceberg_bootstrap()
    try:
        yield
    finally:
        logger.info("AQP API shutting down")
        shutdown_tracing()


app = FastAPI(
    title="Agentic Quant Platform API",
    version="0.3.0",
    description=(
        "Local-first quantitative research + trading API. Drives the agent crew, "
        "backtests, paper / live trading, RL training, and data ingestion. "
        "The Dash monitor is mounted at /dash."
    ),
    lifespan=lifespan,
)

instrument_fastapi(app)

_cors_origins = settings.webui_cors_origin_list or ["*"]
_cors_credentials = _cors_origins != ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Core platform routers -----------------------------------------------
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(agents.router)
app.include_router(agentic.router)
app.include_router(backtest.router)
app.include_router(rl.router)
app.include_router(data.router)
app.include_router(alpha_vantage.router)
app.include_router(portfolio.router)
app.include_router(paper.router)
app.include_router(brokers.router)
app.include_router(strategies.router)
app.include_router(registry.router)
app.include_router(feature_sets.router)
app.include_router(feature_catalog.router)
app.include_router(data_pipelines.router)
app.include_router(data_control.router)
app.include_router(datasets.router)
app.include_router(dbt.router)
app.include_router(entities.router)
app.include_router(market_data_live.router)
app.include_router(factors.router)
app.include_router(ml.router)
app.include_router(metadata_catalog.router)
app.include_router(monitoring.router)
app.include_router(security.router)
app.include_router(visualizations.router)

# --- Data-plane expansion (Phase 5 of the original plan) -----------------
app.include_router(sources.router)
app.include_router(identifiers.router)
app.include_router(datalinks.router)
app.include_router(fred.router)
app.include_router(sec.router)
app.include_router(gdelt.router)

# --- Phase 2 of the agentic-RAG expansion: regulatory data adapters ------
app.include_router(cfpb.router)
app.include_router(fda.router)
app.include_router(uspto.router)

# --- Phase 6 of the agentic-RAG expansion: spec/team/RAG/memory ---------
app.include_router(agent_specs.router)
app.include_router(research_agents.router)
app.include_router(selection_agents.router)
app.include_router(trader_agents.router)
app.include_router(analysis_agents.router)
app.include_router(rag.router)
app.include_router(memory.router)

# --- Data fabric expansion (Phase 5/6/7 of data-fabric expansion) -------
app.include_router(engine_routes.router)
app.include_router(fetcher_routes.router)
app.include_router(entity_registry_routes.router)
app.include_router(dagster_routes.router)
app.include_router(datahub_routes.router)
app.include_router(compute_routes.router)
app.include_router(airbyte.router)
app.include_router(service_manager_routes.router)

# --- Inspiration rehydration: dataset presets library ------------------
app.include_router(dataset_presets.router)

# --- Bot Entity Refactor — first-class bot CRUD + lifecycle -----------
app.include_router(bots_routes.router)

# --- Tenancy / multi-tenant resource ownership -------------------------
app.include_router(orgs_routes.router)
app.include_router(teams_routes.router)
app.include_router(users_routes.router)
app.include_router(workspaces_routes.router)
app.include_router(projects_routes.router)
app.include_router(labs_routes.router)
app.include_router(configs_routes.router)

# --- Data layer expansion (sinks / kafka / flink / producers / proxy) --
app.include_router(sinks_routes.router)
app.include_router(kafka_routes.router)
app.include_router(flink_routes.router)
app.include_router(producers_routes.router)
app.include_router(cluster_mgmt_routes.router)
app.include_router(streaming_links_routes.router)
app.include_router(dataset_loading_agent_routes.router)


# ---------------------------------------------------------------------------
# Dash sub-app mount.
#
# Dash runs on Flask, which speaks WSGI; Starlette ships a WSGIMiddleware that
# adapts it to ASGI so the whole platform lives behind a single Uvicorn worker.
# The mount is best-effort: if Dash isn't installed (e.g. the paper-only
# container), we skip it without breaking the API.
# ---------------------------------------------------------------------------
def _mount_dash() -> None:
    """Try the modern ``a2wsgi`` adapter first, fall back to ``starlette``."""
    try:
        from aqp.ui.dash_app import create_dash_app
    except Exception:  # pragma: no cover — dash not installed
        logger.warning("Dash not installed; /dash mount skipped", exc_info=True)
        return

    try:
        _dash_app = create_dash_app(requests_pathname_prefix="/dash/")
    except Exception:  # pragma: no cover
        logger.warning("Dash factory failed; /dash mount skipped", exc_info=True)
        return

    try:
        from a2wsgi import WSGIMiddleware  # type: ignore[import-not-found]
    except ImportError:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from starlette.middleware.wsgi import WSGIMiddleware  # type: ignore[assignment]

    app.mount("/dash", WSGIMiddleware(_dash_app.server))
    logger.info("Dash monitor mounted at /dash")


_mount_dash()


@app.get("/")
def root() -> dict:
    return {
        "app": "agentic-quant-platform",
        "version": "0.3.0",
        "docs": "/docs",
        "dash": "/dash/",
        "routes": [r.path for r in app.routes if hasattr(r, "path")],
    }
