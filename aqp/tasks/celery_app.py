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
        "aqp.tasks.chat_tasks",
        "aqp.tasks.agentic_backtest_tasks",
        "aqp.tasks.finetune_tasks",
        "aqp.tasks.ingestion_tasks",
        # Phase 3 (data fabric refactor) — feed/catalog sync tasks.
        "aqp.tasks.instrument_catalog_tasks",
        "aqp.tasks.data_sync_tasks",
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
        # Phase 2 (multi-tenant) — interactive user uploads + merge.
        "aqp.tasks.dataset_upload_tasks",
        # Phase 4 — iterative agent-driven optimisation loop.
        "aqp.tasks.optimization_tasks",
        # Bot Entity Refactor — bot lifecycle tasks (backtest / paper / chat / deploy).
        "aqp.tasks.bot_tasks",
        # Visualization layer — Superset/Trino provisioning.
        "aqp.tasks.visualization_tasks",
        # Data layer expansion: scheduling + streaming link refresh.
        "aqp.tasks.streaming_link_tasks",
        # RL layer (FinRL + FinRobot inspired refactor) — runtime-driven tasks.
        "aqp.tasks.rl_tasks",
        # Analysis umbrella (hash-locked AnalysisSpec + flow catalog).
        "aqp.tasks.analysis_flow_tasks",
        # Self-service data fabric — interactive Dagster sandbox (phase 3).
        "aqp.tasks.dagster_sandbox_tasks",
        # HFT / LOB backtest engine (hftbacktest wrapper).
        "aqp.tasks.hft_tasks",
        # Terraform IaC control plane (5th sibling runtime).
        "aqp.tasks.terraform_tasks",
        # Metadata cache refresh (Phase 0): periodic safety-net rebuild
        # so missed write-throughs self-heal.
        "aqp.tasks.cache_tasks",
        # Ownership graph projection (Phase 2): drains the OwnershipEvent
        # bus into Neo4j (or no-ops in postgres mode) and periodic
        # full Postgres -> Neo4j resync for drift recovery.
        "aqp.tasks.ownership_tasks",
        # Phase 4 (analytics rewrite) — heavy QuantStats tearsheet
        # renders + async portfolio metrics.
        "aqp.tasks.analytics_tasks",
        # Phase 5 (agent stall watchdog) — Celery beat task that
        # revokes stalled agent_runs_v2 rows + emits a halt frame.
        "aqp.tasks.agent_watchdog_tasks",
        # Phase 3 (orchestration refactor) — WorkflowRuntime dispatch
        # task + replay helper. Stays harmless when the orchestration
        # flags are off: the task body refuses to enqueue without a
        # resolvable spec.
        "aqp.tasks.orchestration_tasks",
        # Assistant Engine — AssistantRuntime dispatcher. Guarded by
        # ``settings.assistant_engine_enabled``; the body emits a
        # clean ``emit_error`` instead of crashing when the flag is
        # off and the spec lookup misses.
        "aqp.tasks.assistant_tasks",
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
        "aqp.tasks.sync_finance_database": {"queue": "ingest"},
        "aqp.tasks.sync_feed": {"queue": "ingest"},
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
        "aqp.tasks.chat_tasks.*": {"queue": "default"},
        "aqp.tasks.entity_tasks.*": {"queue": "agents"},
        "aqp.tasks.datahub_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.airbyte_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.engine_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.dataset_upload_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.optimization_tasks.*": {"queue": "backtest"},
        "aqp.tasks.data_metadata_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.finops_tasks.*": {"queue": "default"},
        "aqp.tasks.dataset_preset_tasks.*": {"queue": "ingestion"},
        # Phase 4 — analytics tearsheet renders + async metrics.
        "aqp.tasks.analytics_tasks.*": {"queue": "default"},
        # Phase 5 — agent stall watchdog scans on the default queue.
        "aqp.tasks.agent_watchdog_tasks.*": {"queue": "default"},
        # Bot lifecycle: route to the matching execution queues so backtest /
        # paper / chat workloads inherit the existing per-queue capacity caps.
        "aqp.tasks.bot_tasks.run_bot_backtest": {"queue": "backtest"},
        "aqp.tasks.bot_tasks.run_bot_paper": {"queue": "paper"},
        "aqp.tasks.bot_tasks.chat_research_bot": {"queue": "agents"},
        "aqp.tasks.bot_tasks.deploy_bot": {"queue": "default"},
        "aqp.tasks.visualization_tasks.*": {"queue": "ingestion"},
        "aqp.tasks.streaming_link_tasks.*": {"queue": "ingestion"},
        # RL layer (FinRL + FinRobot inspired refactor): RLRuntime-driven tasks
        # share the existing ``training`` queue with the legacy ``train_rl`` /
        # ``evaluate_rl`` tasks; ``paper_trade_rl`` rides on the ``paper`` queue.
        "aqp.tasks.rl_tasks.train_rl_experiment": {"queue": "training"},
        "aqp.tasks.rl_tasks.evaluate_rl_experiment": {"queue": "training"},
        "aqp.tasks.rl_tasks.replay_trajectories": {"queue": "training"},
        "aqp.tasks.rl_tasks.walk_forward_ensemble": {"queue": "training"},
        "aqp.tasks.rl_tasks.best_of_n_search": {"queue": "training"},
        "aqp.tasks.rl_tasks.paper_trade_rl": {"queue": "paper"},
        # Analysis flows: light compute fan-out via the existing agents queue
        # (matches aqp.tasks.analysis_tasks routing for symmetry).
        "aqp.tasks.analysis_flow_tasks.*": {"queue": "agents"},
        # HFT / LOB backtests get their own queue so the slow tick-replay
        # workload doesn't compete for the bar-frequency backtest queue.
        "aqp.tasks.hft_tasks.*": {"queue": "hft"},
        # Terraform IaC lifecycle (5th sibling runtime). Dedicated queue
        # so concurrent plan/apply runs don't compete with backtest /
        # paper workloads, and KEDA can scale ``aqp-celery-terraform-worker``
        # independently of the trading queues.
        "aqp.tasks.terraform_tasks.*": {"queue": "terraform"},
        # Cache refresh is light + frequent; default queue is fine.
        "aqp.tasks.cache_tasks.*": {"queue": "default"},
        # Ownership graph drains are bursty but light; default queue is fine.
        "aqp.tasks.ownership_tasks.*": {"queue": "default"},
        # Orchestration control plane (Phase 3 refactor) — share the
        # agents queue with the legacy ``aqp.tasks.agent_tasks.*``
        # since each workflow run typically wraps an AgentRuntime
        # invocation through one of the registered adapters.
        "aqp.tasks.orchestration_tasks.*": {"queue": "agents"},
        # Assistant Engine dispatcher — same queue as agents /
        # orchestration since it ultimately delegates to one of those
        # runtimes through the AssistantRuntime layer.
        "aqp.tasks.assistant_tasks.*": {"queue": "agents"},
        # Terraform IaC control plane — dedicated queue so the slow
        # ``terraform apply`` (multi-minute) doesn't block bar-cadence
        # work on the default queue. KEDA scales the worker pool from
        # 0 -> AQP_TERRAFORM_MAX_REPLICAS based on queue depth.
        "aqp.tasks.terraform_tasks.*": {"queue": "terraform"},
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
        # Phase 0 — Metadata cache safety-net rebuild. Write-through
        # keeps the cache live during normal operation; this is the
        # drift-recovery / TTL-expiry healer. Interval comes from
        # ``settings.cache_refresh_interval_s`` (default 300 = 5 min).
        "metadata-cache-refresh": {
            "task": "aqp.tasks.cache_tasks.refresh_metadata",
            "schedule": float(getattr(settings, "cache_refresh_interval_s", 300) or 300),
        },
        # Phase 2 — Ownership graph drain. Picks events off the bus
        # and writes them into Neo4j (or no-ops in postgres mode).
        # Short interval keeps the projection ~lagging Postgres by
        # only a couple of seconds during normal operation.
        "ownership-graph-drain": {
            "task": "aqp.tasks.ownership_tasks.drain_events",
            "schedule": 5.0,
        },
        # Phase 2 — Ownership graph full Postgres -> Neo4j resync.
        # Periodic safety-net so any missed event-bus deliveries
        # self-heal. Cheap; runs every 30 min by default.
        "ownership-graph-resync": {
            "task": "aqp.tasks.ownership_tasks.full_resync",
            "schedule": float(
                getattr(settings, "ownership_resync_interval_s", 1800) or 1800
            ),
        },
        # Phase 5 — Agent stall watchdog. Scans ``agent_runs_v2`` for
        # rows that ``AgentRuntime`` will never close (Celery dispatch
        # dropped or runtime hung mid-tool-loop) and halts them
        # cleanly. Interval comes from
        # ``settings.agent_watchdog_period_seconds`` (default 60).
        "agent-stall-watchdog": {
            "task": "aqp.tasks.agent_watchdog_tasks.scan_for_stalled_agent_runs",
            "schedule": float(
                getattr(settings, "agent_watchdog_period_seconds", 60) or 60
            ),
        },
        # Phase 6 (orchestration refactor) — workflow-run watchdog.
        # Mirrors ``agent-stall-watchdog`` for ``workflow_runs`` rows
        # dispatched via ``WorkflowRuntime``. The scan itself stays
        # no-op when ``orchestration_kill_propagation_enabled`` is
        # False so this beat entry being present is harmless on cold
        # installs / pre-rollout deployments.
        "workflow-stall-watchdog": {
            "task": "aqp.tasks.agent_watchdog_tasks.scan_for_stalled_workflow_runs",
            "schedule": float(
                getattr(settings, "agent_watchdog_period_seconds", 60) or 60
            ),
        },
        # Phase 7 (terraform refactor) — drift scan. Opens a ``refresh``
        # run against every active TerraformWorkspace so the /api/infra
        # pane can surface state drift before the next operator-driven
        # apply.
        "terraform-drift-scan": {
            "task": "aqp.tasks.terraform_tasks.terraform_drift_scan",
            "schedule": float(
                getattr(settings, "terraform_drift_scan_period_seconds", 3600) or 3600
            ),
        },
    },
    timezone="UTC",
)


# ---------------------------------------------------------------- Orchestration schedules (Phase 3)
def _register_orchestration_schedules() -> None:
    """Mount workflow YAMLs under ``configs/workflows/`` on the beat schedule.

    Strictly additive — only activates when
    ``settings.orchestration_schedule_enabled`` is ``True`` AND a
    workflow YAML declares ``schedule.enabled: true``. Failures are
    swallowed at DEBUG level so a malformed YAML never blocks Celery
    boot.
    """
    if not getattr(settings, "orchestration_schedule_enabled", False):
        return
    try:
        from pathlib import Path

        from aqp.agents.orchestration.adapters.schedule_adapter import (
            register_schedule_with_celery_beat,
        )
        from aqp.agents.orchestration.spec import load_workflow_specs_from_dir
    except Exception:  # noqa: BLE001 - orchestration package may be unloaded
        logger.debug("orchestration schedule registration skipped", exc_info=True)
        return
    for candidate in (Path("configs/workflows"), Path("aqp/configs/workflows")):
        if not candidate.exists():
            continue
        for spec in load_workflow_specs_from_dir(str(candidate)):
            schedule = getattr(spec, "schedule", None)
            if not schedule or not getattr(schedule, "enabled", False):
                continue
            try:
                register_schedule_with_celery_beat(
                    spec,
                    interval_seconds=float(schedule.interval_seconds or 0) or None,
                    cron=schedule.cron or None,
                )
            except Exception:  # noqa: BLE001
                logger.debug(
                    "failed to register beat schedule for %s",
                    getattr(spec, "name", spec),
                    exc_info=True,
                )
        break


_register_orchestration_schedules()


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


# Phase 3b of the AQP control-plane maturation. Snapshot the active
# :class:`RequestContext` (set by the FastAPI dep
# :func:`aqp.auth.deps.current_context`) onto the task message headers
# so workers running ``SecureTask`` subclasses can rebuild it without
# every dispatch site threading ``user_id`` / ``workspace_id``
# kwargs through. Pre-existing kwargs continue to win — this layer
# only fills the gap where dispatch sites forgot to plumb context.
@before_task_publish.connect
def _attach_request_context_headers(sender=None, headers=None, body=None, **_kwargs):
    """Stamp every dispatch with the active :class:`RequestContext` snapshot.

    Reads the contextvar set by :func:`aqp.auth.contextvars.bind_context`
    on the API thread; writes the resulting flat dict onto the task
    message headers under the ``x-aqp-rctx`` key. Workers using the
    :class:`aqp.tasks.secure_task.SecureTask` base class rebuild the
    context from this header on entry. Skipped when no context is
    bound (CLI-driven dispatch, beat tasks, externally produced
    messages) — the worker falls back to the local-first default.
    """
    if headers is None:
        return
    try:
        from aqp.auth.contextvars import current_request_context

        ctx = current_request_context.get()
        if ctx is None:
            return
        from aqp.tasks.secure_task import RCTX_HEADER_KEY, context_to_headers

        snapshot = context_to_headers(ctx)
        # Defence-in-depth — caller-supplied headers always win.
        existing = headers.get(RCTX_HEADER_KEY)
        if isinstance(existing, dict) and existing.get("user_id"):
            snapshot.update(existing)
        headers[RCTX_HEADER_KEY] = snapshot
    except Exception:  # noqa: BLE001
        return


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
    # Phase 4a of the AQP control-plane maturation — give the worker
    # the same structured JSON logging envelope the API uses. Done
    # per-subprocess so every worker has the OTel trace_id /
    # span_id processor and the RequestContext processor wired in.
    try:
        from aqp.observability.logging import configure_structured_logging

        configure_structured_logging()
    except Exception:  # noqa: BLE001
        logger.warning("worker structured logging not configured", exc_info=True)
    # MLflow autolog hooks are wired lazily to avoid a hard dependency
    # at import time (the tracking URI may not yet be reachable).
    try:
        from aqp.mlops.autolog import register_celery_signals

        register_celery_signals()
    except Exception:  # pragma: no cover — autolog is optional
        logger.debug("MLflow autolog signals not registered", exc_info=True)
    # Ownership-graph SQLAlchemy listener — worker-side commits emit
    # events the drain task will pick up on the next tick. Idempotent.
    try:
        from aqp.graph import install_sqlalchemy_hooks

        install_sqlalchemy_hooks()
    except Exception:  # pragma: no cover — graph layer is optional
        logger.debug("ownership graph hooks not installed in worker", exc_info=True)
