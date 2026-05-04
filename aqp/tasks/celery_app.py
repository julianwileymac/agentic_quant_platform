"""Celery application factory."""
from __future__ import annotations

import logging

from celery import Celery
from celery.signals import (
    before_task_publish,
    task_prerun,
    worker_process_init,
)

from aqp.config import settings
from aqp.observability import configure_tracing, instrument_celery

logger = logging.getLogger(__name__)


_FINOPS_HEADER_KEY = "x-aqp-finops"


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
        "aqp.tasks.ml_test_tasks",
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
        "aqp.tasks.engine_tasks",
        "aqp.tasks.data_metadata_tasks",
        # Phase 5 — FinOps governance audit task.
        "aqp.tasks.finops_tasks",
        # Inspiration rehydration — dataset preset ingestion tasks.
        "aqp.tasks.dataset_preset_tasks",
        # Bot Entity Refactor — bot lifecycle tasks (backtest / paper / chat / deploy).
        "aqp.tasks.bot_tasks",
        # Visualization layer — Superset/Trino provisioning.
        "aqp.tasks.visualization_tasks",
        # Data layer expansion: scheduling + streaming link refresh.
        "aqp.tasks.streaming_link_tasks",
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
        "aqp.tasks.ml_test_tasks.*": {"queue": "ml"},
        "aqp.tasks.optimize_tasks.*": {"queue": "backtest"},
        "aqp.tasks.feature_set_tasks.*": {"queue": "ml"},
        "aqp.tasks.equity_report_tasks.*": {"queue": "agents"},
        "aqp.tasks.llm_tasks.*": {"queue": "default"},
        "aqp.tasks.entity_tasks.*": {"queue": "agents"},
        "aqp.tasks.datahub_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.airbyte_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.engine_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.data_metadata_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.finops_tasks.*": {"queue": "default"},
        "aqp.tasks.dataset_preset_tasks.*": {"queue": "ingestion"},
        # Bot lifecycle: route to the matching execution queues so backtest /
        # paper / chat workloads inherit the existing per-queue capacity caps.
        "aqp.tasks.bot_tasks.run_bot_backtest": {"queue": "backtest"},
        "aqp.tasks.bot_tasks.run_bot_paper": {"queue": "paper"},
        "aqp.tasks.bot_tasks.chat_research_bot": {"queue": "agents"},
        "aqp.tasks.bot_tasks.deploy_bot": {"queue": "default"},
        "aqp.tasks.visualization_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.streaming_link_tasks.*": {"queue": "ingestion"},
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
        # Phase 5 — FinOps governance audit. Scans the cluster for any
        # workload missing the mandatory project / cost_center / owner /
        # data_classification labels and emits an alert so the spend chain
        # back to a strategy_id stays unbroken.
        "finops-tag-audit": {
            "task": "aqp.tasks.finops_tasks.audit",
            "schedule": 6 * 3600.0,
        },
    },
    timezone="UTC",
)


# ---------------------------------------------------------------- FinOps signals
@before_task_publish.connect
def _attach_finops_headers(sender=None, headers=None, body=None, **_kwargs):
    """Stamp every dispatch with :meth:`Settings.finops_labels`.

    Triggered by ``task.delay()`` / ``task.apply_async()`` before the
    Celery transport puts the message on the broker. The headers travel
    with the task so the worker can echo them on its progress emits and
    OTEL spans.

    Application code never has to remember to attach tags — calling
    ``some_task.delay(...)`` is enough; the labels show up downstream
    automatically.
    """
    if headers is None:
        return
    try:
        labels = settings.finops_labels(task_name=str(sender))
    except Exception:  # noqa: BLE001
        return
    # Celery deep-merges this dict; never overwrite caller-supplied keys.
    existing = headers.get(_FINOPS_HEADER_KEY) or {}
    if isinstance(existing, dict):
        labels.update(existing)
    headers[_FINOPS_HEADER_KEY] = labels


@task_prerun.connect
def _record_finops_on_span(sender=None, task_id=None, task=None, **_kwargs):
    """Mirror the FinOps headers onto the active OTEL span and the task obj.

    Hook runs inside the worker just before the task body executes, so
    progress emits + the FastAPI tracing middleware see consistent tags.
    """
    if task is None:
        return
    request = getattr(task, "request", None)
    if request is None:
        return
    headers = getattr(request, "headers", None) or {}
    finops = headers.get(_FINOPS_HEADER_KEY) if isinstance(headers, dict) else None
    if not isinstance(finops, dict) or not finops:
        # Worker received the task without the dispatch hook (e.g. an external
        # producer). Re-stamp from local Settings as a defence-in-depth.
        finops = settings.finops_labels(task_name=str(sender))
    # Make the labels available to ``aqp.tasks._progress.emit`` via attribute.
    try:
        setattr(task, "_aqp_finops", dict(finops))
    except Exception:  # noqa: BLE001
        pass
    try:
        from opentelemetry import trace  # type: ignore[import-not-found]

        span = trace.get_current_span()
        if span is not None and span.is_recording():
            for k, v in finops.items():
                span.set_attribute(f"aqp.finops.{k}", str(v))
    except Exception:  # pragma: no cover — OTEL is optional
        return


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
