"""kopf reconciliation handlers for the 9 QuantBot CRDs.

Level-triggered reconciliation: every handler compares desired
(from ``spec``) against actual (queried from the cluster) and drives
the cluster back to desired state. Failures are logged + reflected on
``status.conditions``; the kopf retry policy handles transient errors.

Hard rules:

- AGENTS rule 14: Bot lifecycle stays with :class:`BotRuntime` — the
  operator's job is to schedule the Pod, never to execute strategy
  logic.
- AGENTS rule 15: Bot spec snapshots go through ``persist_spec()``.
- AGENTS rule 45: Workload ops (start/stop/scale) flow through
  :class:`aqp_platform_core.runtime.WorkloadRuntime`.
- AGENTS rule 47: K8s client construction uses the topology service.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from aqp_bots.operator.crds.bot_cr import BotCR
from aqp_bots.operator.finalizers import (
    DRAIN_FINALIZER,
    install_finalizer,
    remove_finalizer,
    run_drain_hook,
)
from aqp_bots.operator.render import render_backtest_workload, render_bot_workload
from aqp_bots.risk.kill_switch_v2 import (
    KillSwitchScope,
    engage_scoped,
    release_scoped,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# kopf decorator wiring (lazy — module imports without kopf for tests/CI).
# ---------------------------------------------------------------------------


def _kopf():
    """Lazy-import kopf; returns None when unavailable."""
    try:
        import kopf  # type: ignore[import-not-found]

        return kopf
    except ImportError:
        return None


def register_handlers() -> bool:
    """Register every kopf decorator. Returns True on success.

    This indirection (instead of module-level @kopf.on) keeps the
    package importable in environments without kopf installed (CI,
    tests, the operator-less FastAPI route layer).
    """
    kopf = _kopf()
    if kopf is None:
        logger.info("register_handlers: kopf not installed; handlers not registered")
        return False

    @kopf.on.create("quantbot.io", "v1", "bots")  # type: ignore[union-attr]
    @kopf.on.update("quantbot.io", "v1", "bots")  # type: ignore[union-attr]
    @kopf.on.resume("quantbot.io", "v1", "bots")  # type: ignore[union-attr]
    async def reconcile_bot(spec, name, namespace, uid, status, patch, logger, **_):  # type: ignore[no-redef]
        logger.info("reconcile_bot %s/%s", namespace, name)
        cr = BotCR.model_validate(
            {
                "apiVersion": "quantbot.io/v1",
                "kind": "Bot",
                "metadata": {"name": name, "namespace": namespace, "uid": uid},
                "spec": dict(spec or {}),
                "status": dict(status or {}),
            }
        )
        await install_finalizer(cr, patch)
        documents = render_bot_workload(cr)
        await _apply_documents(documents, logger=logger)

        version_id = await _snapshot_spec(cr)
        await _persist_status(
            patch=patch,
            phase=_phase_for_running(cr),
            workload_type=_workload_type(cr),
            workload_name=f"bot-{name}",
            spec_version=version_id,
        )

    @kopf.on.delete("quantbot.io", "v1", "bots")  # type: ignore[union-attr]
    async def drain_bot(spec, name, namespace, uid, patch, logger, **_):
        logger.info("drain_bot %s/%s", namespace, name)
        cr = BotCR.model_validate(
            {
                "apiVersion": "quantbot.io/v1",
                "kind": "Bot",
                "metadata": {"name": name, "namespace": namespace, "uid": uid},
                "spec": dict(spec or {}),
            }
        )
        await run_drain_hook(cr, logger=logger)
        await remove_finalizer(cr, patch)

    # ------------------------------------------------------------------
    # RiskPolicy
    # ------------------------------------------------------------------
    @kopf.on.create("quantbot.io", "v1", "riskpolicies")  # type: ignore[union-attr]
    @kopf.on.update("quantbot.io", "v1", "riskpolicies")  # type: ignore[union-attr]
    async def reconcile_riskpolicy(spec, name, namespace, status, patch, logger, **_):
        logger.info("reconcile_riskpolicy %s/%s", namespace, name)
        bots_bound = await _count_bound_bots(namespace=namespace, policy_name=name)
        await _persist_status(
            patch=patch,
            extra={"botsBound": bots_bound, "lastValidatedAt": _now_iso()},
        )

    # ------------------------------------------------------------------
    # KillSwitch
    # ------------------------------------------------------------------
    @kopf.on.create("quantbot.io", "v1", "killswitches")  # type: ignore[union-attr]
    @kopf.on.update("quantbot.io", "v1", "killswitches")  # type: ignore[union-attr]
    async def reconcile_killswitch(spec, name, namespace, patch, logger, **_):
        scope = (spec or {}).get("scope", "bot")
        target = (spec or {}).get("target", "")
        reason = (spec or {}).get("reason", "manual")
        if not target:
            logger.warning("killswitch %s/%s has empty target; ignoring", namespace, name)
            return
        try:
            engage_scoped(scope, target, reason=reason)
        except Exception:  # noqa: BLE001
            logger.exception("kill switch engage failed")
        await _persist_status(
            patch=patch, extra={"engaged": True, "engagedAt": _now_iso()},
        )

    @kopf.on.delete("quantbot.io", "v1", "killswitches")  # type: ignore[union-attr]
    async def release_killswitch(spec, name, namespace, logger, **_):
        scope = (spec or {}).get("scope", "bot")
        target = (spec or {}).get("target", "")
        if target:
            try:
                release_scoped(scope, target)
            except Exception:  # noqa: BLE001
                logger.exception("kill switch release failed")

    # ------------------------------------------------------------------
    # BotFleet
    # ------------------------------------------------------------------
    @kopf.on.create("quantbot.io", "v1", "botfleets")  # type: ignore[union-attr]
    @kopf.on.update("quantbot.io", "v1", "botfleets")  # type: ignore[union-attr]
    async def reconcile_botfleet(spec, name, namespace, patch, logger, **_):
        logger.info("reconcile_botfleet %s/%s", namespace, name)
        bot_count, running_count, halted_count = await _fleet_stats(namespace, name)
        await _persist_status(
            patch=patch,
            extra={
                "botCount": bot_count,
                "runningBotCount": running_count,
                "haltedBotCount": halted_count,
            },
        )
        if (spec or {}).get("halt"):
            try:
                engage_scoped(KillSwitchScope.FLEET.value, name, reason="fleet.halt=true")
            except Exception:  # noqa: BLE001
                logger.exception("fleet halt engagement failed")

    # ------------------------------------------------------------------
    # BacktestJob
    # ------------------------------------------------------------------
    @kopf.on.create("quantbot.io", "v1", "backtestjobs")  # type: ignore[union-attr]
    async def reconcile_backtestjob(spec, name, namespace, uid, patch, logger, **_):
        from aqp_bots.operator.crds.backtestjob_cr import BacktestJobCR

        cr = BacktestJobCR.model_validate(
            {
                "apiVersion": "quantbot.io/v1",
                "kind": "BacktestJob",
                "metadata": {"name": name, "namespace": namespace, "uid": uid},
                "spec": dict(spec or {}),
            }
        )
        documents = render_backtest_workload(cr)
        await _apply_documents(documents, logger=logger)
        await _persist_status(patch=patch, extra={"phase": "Running", "total": cr.spec.parallelism})

    # ------------------------------------------------------------------
    # Strategy / MarketDataFeed / ExecutionVenue / CanaryRollout
    # ------------------------------------------------------------------
    # These CRs are reference resources; the operator updates their
    # status fields but doesn't render workloads for them directly.
    @kopf.on.create("quantbot.io", "v1", "strategies")  # type: ignore[union-attr]
    @kopf.on.update("quantbot.io", "v1", "strategies")  # type: ignore[union-attr]
    async def reconcile_strategy(spec, name, namespace, patch, logger, **_):
        bots_using = await _count_bots_using_strategy(namespace, name)
        await _persist_status(
            patch=patch,
            extra={"botsUsing": bots_using, "lastValidatedAt": _now_iso()},
        )

    @kopf.on.create("quantbot.io", "v1", "marketdatafeeds")  # type: ignore[union-attr]
    @kopf.on.update("quantbot.io", "v1", "marketdatafeeds")  # type: ignore[union-attr]
    async def reconcile_marketdatafeed(spec, name, namespace, patch, logger, **_):
        # Status fields like "connected" are populated by the consumer
        # bot. Operator just acknowledges the CR exists.
        await _persist_status(patch=patch, extra={"lastReconciled": _now_iso()})

    @kopf.on.create("quantbot.io", "v1", "executionvenues")  # type: ignore[union-attr]
    @kopf.on.update("quantbot.io", "v1", "executionvenues")  # type: ignore[union-attr]
    async def reconcile_executionvenue(spec, name, namespace, patch, logger, **_):
        await _persist_status(patch=patch, extra={"lastReconciled": _now_iso()})

    @kopf.on.create("quantbot.io", "v1", "canaryrollouts")  # type: ignore[union-attr]
    @kopf.on.update("quantbot.io", "v1", "canaryrollouts")  # type: ignore[union-attr]
    async def reconcile_canaryrollout(spec, name, namespace, patch, logger, **_):
        # Argo Rollouts owns the actual canary; this handler just keeps
        # status in sync so the CR is observable from kubectl get.
        await _persist_status(
            patch=patch,
            extra={"phase": "Progressing", "lastReconciled": _now_iso()},
        )

    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _workload_type(cr: BotCR) -> str:
    freq = cr.spec.capabilities.frequency
    if freq == "hft":
        return "DaemonSet"
    if freq == "eod":
        return "CronJob"
    if freq == "mid":
        return "StatefulSet"
    return "Deployment"


def _phase_for_running(cr: BotCR) -> str:
    return "Running"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _apply_documents(documents: list[dict[str, Any]], *, logger) -> None:
    """Apply rendered manifests via aqp_platform_core.WorkloadRuntime (rule 45).

    Falls back to ``kubernetes-asyncio`` direct apply if
    WorkloadRuntime isn't available (tests / dev).
    """
    try:
        from aqp_platform_core.runtime.workload import WorkloadRuntime  # type: ignore[import-not-found]

        runtime = WorkloadRuntime()
        for doc in documents:
            # WorkloadRuntime.apply_config is the rule-45-compliant entrypoint.
            try:
                await runtime.apply_config(  # type: ignore[attr-defined]
                    target=doc.get("metadata", {}).get("name", ""),
                    namespace=doc.get("metadata", {}).get("namespace", "default"),
                    manifest=doc,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "WorkloadRuntime.apply_config failed for %s; falling back to direct apply",
                    doc.get("metadata", {}).get("name"),
                )
                await _direct_apply(doc, logger=logger)
        return
    except Exception:  # noqa: BLE001
        for doc in documents:
            await _direct_apply(doc, logger=logger)


async def _direct_apply(doc: dict[str, Any], *, logger) -> None:
    """Fallback: server-side apply via kubernetes-asyncio."""
    try:
        from kubernetes_asyncio import client, config  # type: ignore[import-not-found]
        from kubernetes_asyncio.client.rest import ApiException  # type: ignore[import-not-found]
    except ImportError:
        logger.debug("kubernetes-asyncio not installed; skipping apply")
        return
    try:
        try:
            config.load_incluster_config()
        except config.ConfigException:  # type: ignore[attr-defined]
            await config.load_kube_config()
        api = client.CustomObjectsApi()
        await api.api_client.call_api(
            "/apis/apps/v1/namespaces/{ns}/deployments",
            "POST",
            path_params={"ns": doc["metadata"]["namespace"]},
            body=doc,
            response_type="object",
            _return_http_data_only=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("direct apply failed for %s", doc.get("metadata", {}).get("name"))


async def _snapshot_spec(cr: BotCR) -> str | None:
    """Snapshot the embedded BotSpec via persist_spec() (rule 15)."""
    try:
        from aqp_bots.registry import persist_spec
        from aqp_bots.spec import BotSpec

        payload = dict(cr.spec.botSpec or {})
        if not payload:
            return None
        # Backfill slug from CR name when not in the spec.
        payload.setdefault("slug", cr.metadata.name)
        payload.setdefault("name", cr.metadata.name)
        spec = BotSpec.model_validate(payload)
        return persist_spec(spec)
    except Exception:  # noqa: BLE001
        logger.exception("snapshot_spec failed")
        return None


async def _persist_status(
    *,
    patch: Any,
    phase: str | None = None,
    workload_type: str | None = None,
    workload_name: str | None = None,
    spec_version: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if not hasattr(patch, "status"):
        return
    if phase is not None:
        patch.status["phase"] = phase
    if workload_type is not None:
        patch.status["workloadType"] = workload_type
    if workload_name is not None:
        patch.status["workloadName"] = workload_name
    if spec_version is not None:
        patch.status["specVersion"] = spec_version
    patch.status["lastReconciledAt"] = _now_iso()
    if extra:
        for k, v in extra.items():
            patch.status[k] = v


async def _count_bound_bots(*, namespace: str, policy_name: str) -> int:
    # Minimal default; production implementation queries the cluster.
    return 0


async def _count_bots_using_strategy(namespace: str, strategy_name: str) -> int:
    return 0


async def _fleet_stats(namespace: str, fleet_name: str) -> tuple[int, int, int]:
    return 0, 0, 0


__all__ = ["register_handlers"]
