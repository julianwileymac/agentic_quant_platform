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
    agent_health as agent_health_routes,
    agent_specs,
    agentic,
    agents,
    alpha_vantage,
    analysis as analysis_routes,
    analysis_agents,
    analytics_ml as analytics_ml_routes,
    analytics_portfolio as analytics_portfolio_routes,
    airbyte,
    airbyte_builder as airbyte_builder_routes,
    auth,
    backtest,
    bots as bots_routes,
    brokers,
    cache as cache_routes,
    cfpb,
    chat,
    dagster_sandbox as dagster_sandbox_routes,
    data,
    data_control,
    data_entities,
    data_pipelines,
    datalinks,
    datasets,
    dataset_presets,
    discovery as discovery_routes,
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
    ingest_wizard as ingest_wizard_routes,
    lob_backtest as lob_backtest_routes,
    market_data_live,
    memory,
    metadata_catalog,
    metadata_aspects as metadata_aspects_routes,
    ml,
    monitoring,
    orders as orders_routes,
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
    feeds as feeds_routes,
    instrument_catalog as instrument_catalog_routes,
    lineage as lineage_routes,
    orchestration as orchestration_routes,
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
# Phase 1 — Experiments + Tests umbrella + polymorphic Resources.
from aqp.api.routes import (  # noqa: E402
    experiments as experiments_routes,
    resources as resources_routes,
    tests as tests_routes,
)
# Phase 4 — Auth0 Action sync endpoint for custom-claim injection.
from aqp.api.routes import (  # noqa: E402
    auth0_sync as auth0_sync_routes,
)
# SCIM 2.0 provisioning endpoint for Auth0 / enterprise IdP sync.
from aqp.api.routes import (  # noqa: E402
    scim as scim_routes,
)
# Account management surface — /me/* routes
from aqp.api.routes import (  # noqa: E402
    me as me_routes,
)
# Tenancy invites — protected CRUD + public token-accept (Phase 7 account mgmt).
from aqp.api.routes import (  # noqa: E402
    invites as invites_routes,
)
# Phase 7 — MSAL / Entra ID sync endpoint + tenancy onboarding routes.
from aqp.api.routes import (  # noqa: E402
    msal_sync as msal_sync_routes,
    tenancy as tenancy_routes,
)
# Phase 7 — Terraform IaC control plane (REST + WS) + /infra dashboard +
# the high-level /control-plane API consumed by the Vite Control Plane UI.
from aqp.api.routes import (  # noqa: E402
    infra as infra_routes,
    terraform as terraform_routes,
)
from aqp.api.routes import (  # noqa: E402
    control_plane as control_plane_routes,
)
# Phase 7 — LEAN strategy template catalog + clone-to-workspace REST.
from aqp.api.routes import (  # noqa: E402
    strategy_templates as strategy_templates_routes,
)
# Hybrid agentic-RL Phase 4 — Alpha Researcher + Strategy Executor REST.
from aqp.api.routes import (  # noqa: E402
    quant_agents as quant_agents_routes,
)
from aqp.api.routes import (  # noqa: E402
    workflows as workflows_routes,
)
# Phase 3 (assistant engine) — interactive AssistantRuntime over
# AgentRuntime / WorkflowRuntime. Mounts unconditionally; routes gate
# on settings.assistant_engine_enabled and return 503 when off so the
# legacy /chat surface is untouched.
from aqp.api.routes import (  # noqa: E402
    assistants as assistants_routes,
)
# Data Lab — four-mode GraphSpec workspace (EDA / Testing / Evaluation /
# Simulation). REST + WebSocket surface, gated by settings.aqp_lab_enabled.
from aqp.api.routes import (  # noqa: E402
    lab as lab_routes,
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

# Phase 2d of the AQP infra-expansion plan: Phoenix observability for
# LLM / agent / RAG spans. Runs alongside (not in place of) the OTel
# tracing pipeline; Phoenix's auto-instrumentation tags spans with
# OpenInference attributes so the Otel gateway routes them to Phoenix
# while keeping infra spans on Tempo.
try:
    from aqp.observability.phoenix import configure_phoenix_for_app

    configure_phoenix_for_app()
except Exception:  # noqa: BLE001
    logger.warning(
        "Phoenix bootstrap failed for the API process; continuing without it",
        exc_info=True,
    )

# Phase 4a of the AQP control-plane maturation — structured JSON
# logging with auto-injected OpenTelemetry trace_id + span_id and
# ``request_id`` from the correlation-id middleware. Routing structlog
# through the stdlib logging chain means every existing
# ``logging.getLogger(__name__).info(...)`` callsite picks up the JSON
# envelope without code changes.
try:
    from aqp.observability.logging import configure_structured_logging

    configure_structured_logging(level=settings.env != "production" and "INFO" or "INFO")
except Exception:  # noqa: BLE001
    logging.getLogger(__name__).warning(
        "structured logging configuration failed; falling back to stdlib defaults",
        exc_info=True,
    )


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


def _maybe_install_m2m_store() -> None:
    """Plug the :class:`M2MStore` into the credential resolver when enabled.

    Activates when ``AQP_AUTH_M2M_ENABLED=true`` and the configured
    :class:`IdentityProvider` supports ``client_credentials``. Failure
    is logged but never blocks startup; with M2M off the resolver still
    reads bootstrap-minted file payloads + env defaults.
    """
    if not getattr(settings, "auth_m2m_enabled", False):
        return
    try:
        from aqp.auth.m2m import install_m2m_store

        install_m2m_store()
    except Exception:  # noqa: BLE001
        logger.exception("M2M store install failed; resolver will fall back to file/env stores")


def _maybe_prefetch_metadata_cache() -> None:
    """Warm the metadata cache so EntityPicker dropdowns are instant."""
    if not getattr(settings, "cache_enabled", True):
        return
    try:
        from aqp.cache.lifespan import prefetch_at_startup

        prefetch_at_startup()
    except Exception:  # noqa: BLE001
        logger.exception(
            "metadata cache prefetch failed; UI dropdowns may be empty until a write-through fires",
        )


def _install_ownership_graph_hooks() -> None:
    """Register the SQLAlchemy after_flush_postexec listener for ownership events.

    The listener translates tenancy / experiment / resource mutations
    into :class:`OwnershipEvent` rows on the bus. Idempotent; safe to
    re-run. The drain task (:mod:`aqp.tasks.ownership_tasks`) handles
    the projection into Neo4j when ``AQP_OWNERSHIP_GRAPH_STORE=neo4j``.
    """
    try:
        from aqp.graph import install_sqlalchemy_hooks

        install_sqlalchemy_hooks()
    except Exception:  # noqa: BLE001
        logger.exception(
            "ownership graph hook install failed; multi-hop ownership reads "
            "will rely on the periodic full_resync until next restart",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AQP API starting | env=%s", settings.env)
    _maybe_run_iceberg_bootstrap()
    _maybe_install_m2m_store()
    _maybe_prefetch_metadata_cache()
    _install_ownership_graph_hooks()
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
# Phase 4a — correlation IDs + structured request logging.
# Order matters: CorrelationIDMiddleware MUST run BEFORE
# StructuredLoggingMiddleware so the request_id is bound to
# structlog's contextvars before the request log line is emitted.
# Starlette executes middleware in REVERSE registration order (LIFO),
# so we register StructuredLoggingMiddleware first, then
# CorrelationIDMiddleware on top.
try:
    from aqp.api.middleware import (
        CorrelationIDMiddleware,
        StructuredLoggingMiddleware,
    )

    app.add_middleware(StructuredLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)
except Exception as exc:  # noqa: BLE001
    logging.getLogger(__name__).warning(
        "correlation/log middleware not registered: %s", exc
    )

# --- Core platform routers -----------------------------------------------
app.include_router(health.router)
app.include_router(auth.router)
# Management Engine Phase E — additive BFF auth surface
# (/auth/providers + /auth/refresh).
try:
    from aqp.api.routes import auth_bff as auth_bff_routes  # noqa: E402

    app.include_router(auth_bff_routes.router)
except Exception as exc:  # noqa: BLE001
    logging.getLogger(__name__).warning(
        "auth_bff router unavailable (%s); /auth/providers + /auth/refresh disabled",
        exc,
    )
# Trust X-Forwarded-* on the Auth0FastAPI DPoP path. No-op when the
# auth0-fastapi-api SDK is not present.
try:
    from aqp.auth.auth0_fastapi import configure_auth0_fastapi_on_app

    configure_auth0_fastapi_on_app(app)
except Exception as exc:  # noqa: BLE001
    logging.getLogger(__name__).debug("Auth0FastAPI trust_proxy not configured: %s", exc)
app.include_router(scim_routes.router)
app.include_router(me_routes.router)
app.include_router(invites_routes.router)
app.include_router(invites_routes.public_router)
app.include_router(chat.router)
app.include_router(agents.router)
app.include_router(control_plane_routes.router)
app.include_router(agentic.router)
app.include_router(backtest.router)
app.include_router(lob_backtest_routes.router)
app.include_router(rl.router)
app.include_router(data.router)
app.include_router(alpha_vantage.router)
app.include_router(portfolio.router)
app.include_router(paper.router)
app.include_router(brokers.router)
app.include_router(orders_routes.router)
# Phase 7 — register the more specific ``/strategies/templates`` router
# BEFORE the catch-all ``/strategies/{strategy_id}`` so the LEAN
# template catalog isn't shadowed by the existing strategy CRUD.
app.include_router(strategy_templates_routes.router)
app.include_router(quant_agents_routes.router)
app.include_router(strategies.router)
app.include_router(registry.router)
app.include_router(feature_sets.router)
app.include_router(feature_catalog.router)
app.include_router(data_pipelines.router)
app.include_router(data_control.router)
app.include_router(data_entities.router)
app.include_router(datasets.router)
app.include_router(dbt.router)
app.include_router(entities.router)
app.include_router(market_data_live.router)
app.include_router(factors.router)
app.include_router(ml.router)
app.include_router(metadata_catalog.router)
app.include_router(
    metadata_aspects_routes.router,
    prefix="/metadata/aspects",
    tags=["metadata"],
)
app.include_router(cache_routes.router)
app.include_router(discovery_routes.router)
app.include_router(dagster_sandbox_routes.router)
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
# Phase 5 (orchestration refactor) — interactive workflow studio API.
# Mounts unconditionally; each route gates on
# settings.orchestration_studio_enabled and returns 503 when off so
# existing routes are completely unaffected.
app.include_router(workflows_routes.router)
# Assistant Engine (Phase 3) — dispatcher + WS stream. Each route gates
# on settings.assistant_engine_enabled.
app.include_router(assistants_routes.router)
# Data Lab — mount the REST + WS routers behind the master flag so
# the API surface stays a no-op when the operator hasn't opted in.
if getattr(settings, "aqp_lab_enabled", False):
    app.include_router(lab_routes.router)
    app.include_router(lab_routes.ws_router)
app.include_router(selection_agents.router)
app.include_router(trader_agents.router)
app.include_router(analysis_agents.router)
app.include_router(rag.router)
app.include_router(memory.router)

# --- Analysis umbrella (hash-locked AnalysisSpec + flow catalog) -------
app.include_router(analysis_routes.router)
app.include_router(analytics_portfolio_routes.router)
app.include_router(analytics_ml_routes.router)
app.include_router(agent_health_routes.router)

# --- Data fabric expansion (Phase 5/6/7 of data-fabric expansion) -------
app.include_router(engine_routes.router)
app.include_router(fetcher_routes.router)
app.include_router(entity_registry_routes.router)
app.include_router(dagster_routes.router)
app.include_router(datahub_routes.router)
app.include_router(compute_routes.router)
app.include_router(ingest_wizard_routes.router)
app.include_router(airbyte.router)
app.include_router(airbyte_builder_routes.router)
app.include_router(service_manager_routes.router)
app.include_router(feeds_routes.router, prefix="/api/v1/feeds", tags=["feeds"])
app.include_router(
    instrument_catalog_routes.router,
    prefix="/api/v1/instruments",
    tags=["instruments"],
)
app.include_router(
    orchestration_routes.router,
    prefix="/api/v1/orchestration",
    tags=["orchestration"],
)
app.include_router(lineage_routes.router, prefix="/api/v1/lineage", tags=["lineage"])

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

# --- Phase 1 — Experiments + Tests umbrella + polymorphic Resources ---
app.include_router(experiments_routes.router)
app.include_router(tests_routes.router)
app.include_router(resources_routes.router)

# --- Phase 4 — Auth0 Action sync endpoint ----------------------------
app.include_router(auth0_sync_routes.router)
# --- Phase 7 — MSAL / Entra ID sync endpoint + tenancy onboarding ----
app.include_router(msal_sync_routes.router)
app.include_router(tenancy_routes.router)
# --- Phase 7 — Terraform IaC control plane + /infra dashboard --------
app.include_router(terraform_routes.router)
app.include_router(terraform_routes.ws_router)
app.include_router(infra_routes.router)
app.include_router(infra_routes.ws_router)
# Phase 2b of the AQP control-plane maturation — kill-switch fan-out for
# the WorkloadRuntime (AGENTS rule 45). Mirrors the sidecar
# ``aqp_control_plane`` ``/manage/workloads/halt`` endpoint so the
# frontend KillSwitch component reaches the same surface in both
# embedded and sidecar deployment modes.
try:
    from aqp.api.routes import workloads as workloads_routes  # noqa: E402

    app.include_router(workloads_routes.router)
except Exception as exc:  # noqa: BLE001
    logging.getLogger(__name__).warning(
        "workloads router not loaded: %s", exc
    )
# Management Engine — Cloudflare edge (tunnels / DNS / Access apps).
try:
    from aqp.api.routes import cloudflare as cloudflare_routes  # noqa: E402

    app.include_router(cloudflare_routes.router)
except Exception as exc:  # noqa: BLE001
    logging.getLogger(__name__).warning(
        "cloudflare router unavailable (%s); /cloudflare/* endpoints disabled",
        exc,
    )
# (control_plane_routes.router is registered earlier alongside auth /
# scim / me / invites; rule 45 — high-level /control-plane API for the
# Vite UI delegates to TerraformRuntime + KubernetesAdapter.)
# (Phase 7 strategy_templates router is registered earlier, BEFORE
# ``strategies.router``, so the ``/strategies/templates`` prefix isn't
# shadowed by ``/strategies/{strategy_id}``.)

# --- Data layer expansion (sinks / kafka / flink / producers / proxy) --
app.include_router(sinks_routes.router)
app.include_router(kafka_routes.router)
app.include_router(flink_routes.router)
app.include_router(producers_routes.router)
app.include_router(cluster_mgmt_routes.router)
app.include_router(cluster_mgmt_routes.legacy_router)
app.include_router(streaming_links_routes.router)
app.include_router(dataset_loading_agent_routes.router)


# --- Data layer unification: external MCP server router ----------------
# Exposes DATA_MCP_TOOLS via streamable HTTP so external clients
# (Cursor, Claude Desktop, etc.) can call them through the same
# tool catalog the in-process AgentRuntime uses via the bridge.
try:
    from aqp.data.mcp.server import build_mcp_router as _build_data_mcp_router

    app.include_router(_build_data_mcp_router())
except Exception:  # noqa: BLE001 - MCP server is optional at boot
    logger.warning("DataMCP HTTP router not mounted", exc_info=True)


# --- Codebase MCP server router ----------------------------------------
# Mirrors /mcp/data. Exposes CODEBASE_MCP_TOOLS (codebase.search /
# codebase.get_repo_graph / codebase.find_definition /
# codebase.find_references / codebase.elaborate_finding) via streamable
# HTTP so Cursor / Claude Desktop / external scripts can navigate the
# AQP repository through the same tool catalog AgentRuntime sees via
# the bridge.
try:
    from aqp.codebase.mcp.server import (
        build_codebase_mcp_router as _build_codebase_mcp_router,
    )

    app.include_router(_build_codebase_mcp_router())
except Exception:  # noqa: BLE001 - codebase MCP is optional at boot
    logger.warning("CodebaseMCP HTTP router not mounted", exc_info=True)


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


# ---------------------------------------------------------------------------
# Refactor — unified aqp_client gateway (Phase 3).
#
# When AQP_CLIENT_MODE=true the same FastAPI process additionally serves
# the Vite SPA at /, the Solara legacy UI at /legacy, the rollback Next.js
# bundle at /webui, and reverse-proxies /api, /ml, /mcp, /manage, /ws/* to
# the backend services addressed by ConnectivityConfig.
#
# When AQP_CLIENT_MODE is unset / false this is a no-op so the existing
# AQP API container behaviour is unchanged.
# ---------------------------------------------------------------------------
def _install_client_mode() -> None:
    try:
        from aqp.api.client_routes import install_client_surfaces

        install_client_surfaces(app)
    except Exception:  # noqa: BLE001
        logger.exception(
            "aqp_client mode install failed; SPA / proxy / Solara mounts skipped"
        )


_install_client_mode()


# ``/`` is the root informational endpoint when client mode is OFF.
# In client mode the SPA fallback in client_routes.py owns / via a
# catch-all route registered AFTER this one. FastAPI's matcher is
# greedy on more-specific paths, so this exact-/ route still wins
# when both are registered.
@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "app": "agentic-quant-platform",
        "version": "0.3.0",
        "docs": "/docs",
        "dash": "/dash/",
        "client_mode": __import__("os").environ.get("AQP_CLIENT_MODE", "").lower() in {"1", "true", "yes", "on"},
        "routes": [r.path for r in app.routes if hasattr(r, "path")],
    }
