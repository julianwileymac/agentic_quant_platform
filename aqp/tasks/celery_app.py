"""Celery application factory."""
from __future__ import annotations

import logging

from celery import Celery
from celery.signals import worker_process_init

from aqp.config import settings
from aqp.observability import configure_tracing, instrument_celery

logger = logging.getLogger(__name__)


celery_app = Celery(
    "aqp",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "aqp.tasks.backtest_tasks",
        "aqp.tasks.training_tasks",
        "aqp.tasks.agent_tasks",
        "aqp.tasks.agentic_backtest_tasks",
        "aqp.tasks.finetune_tasks",
        "aqp.tasks.ingestion_tasks",
        "aqp.tasks.paper_tasks",
        "aqp.tasks.factor_tasks",
        "aqp.tasks.ml_tasks",
        "aqp.tasks.optimize_tasks",
        "aqp.tasks.feature_set_tasks",
        "aqp.tasks.equity_report_tasks",
        "aqp.tasks.llm_tasks",
        # New: regulatory data ingestion (CFPB / FDA / USPTO)
        "aqp.tasks.regulatory_tasks",
        # New: hierarchical RAG indexing + Raptor summarisation
        "aqp.tasks.rag_tasks",
        # New: agent-team runners (research / selection / trader / analysis)
        "aqp.tasks.research_tasks",
        "aqp.tasks.selection_tasks",
        "aqp.tasks.analysis_tasks",
        # Data fabric expansion: entity registry + DataHub sync.
        "aqp.tasks.entity_tasks",
        "aqp.tasks.datahub_tasks",
        "aqp.tasks.airbyte_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_routes={
        "aqp.tasks.backtest_tasks.*": {"queue": "backtest"},
        "aqp.tasks.training_tasks.*": {"queue": "training"},
        "aqp.tasks.agent_tasks.*": {"queue": "agents"},
        "aqp.tasks.agentic_backtest_tasks.*": {"queue": "agents"},
        "aqp.tasks.finetune_tasks.*": {"queue": "training"},
        "aqp.tasks.ingestion_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.regulatory_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.rag_tasks.*": {"queue": "rag"},
        "aqp.tasks.research_tasks.*": {"queue": "agents"},
        "aqp.tasks.selection_tasks.*": {"queue": "agents"},
        "aqp.tasks.analysis_tasks.*": {"queue": "agents"},
        "aqp.tasks.paper_tasks.*": {"queue": "paper"},
        "aqp.tasks.factor_tasks.*": {"queue": "factors"},
        "aqp.tasks.ml_tasks.*": {"queue": "ml"},
        "aqp.tasks.optimize_tasks.*": {"queue": "backtest"},
        "aqp.tasks.feature_set_tasks.*": {"queue": "ml"},
        "aqp.tasks.equity_report_tasks.*": {"queue": "agents"},
        "aqp.tasks.llm_tasks.*": {"queue": "default"},
        "aqp.tasks.entity_tasks.*": {"queue": "agents"},
        "aqp.tasks.datahub_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.airbyte_tasks.*": {"queue": "ingestion"},
    },
    beat_schedule={
        "drift-check": {
            "task": "aqp.tasks.agent_tasks.drift_check",
            "schedule": 3600.0,
        },
        "rag-refresh-l0-alpha-base": {
            "task": "aqp.tasks.rag_tasks.refresh_l0_alpha_base",
            "schedule": 6 * 3600.0,
        },
    },
    timezone="UTC",
)


# Tracing must be initialised per worker subprocess (not at module import),
# otherwise importing ``celery_app`` from the API — which transitively
# imports task modules — would hijack the API's service.name.
@worker_process_init.connect
def _configure_worker_tracing(*_args, **_kwargs):
    configure_tracing(service_name=f"{settings.otel_service_name}-worker")
    instrument_celery()
    # MLflow autolog hooks are wired lazily to avoid a hard dependency
    # at import time (the tracking URI may not yet be reachable).
    try:
        from aqp.mlops.autolog import register_celery_signals

        register_celery_signals()
    except Exception:  # pragma: no cover — autolog is optional
        logger.debug("MLflow autolog signals not registered", exc_info=True)
