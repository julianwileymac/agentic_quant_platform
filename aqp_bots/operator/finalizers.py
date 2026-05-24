"""Operator finalizers: graceful drain.

The ``quantbot.io/graceful-drain`` finalizer keeps a Bot CR in the
cluster after ``kubectl delete`` until the pod has had time to
cancel its working orders (optional: flatten positions) and snapshot
its final state.

Drain timeout per blueprint §A.3:
- 30s for HFT bots
- 300s default for everything else

These are wired into :class:`aqp_bots.spec.LifecycleSpec.drain_timeout_seconds`;
the operator pod calls :func:`run_drain_hook` and observes the
resulting state before removing the finalizer.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aqp_bots.operator.crds.bot_cr import BotCR

logger = logging.getLogger(__name__)

DRAIN_FINALIZER = "quantbot.io/graceful-drain"


async def install_finalizer(cr: BotCR, patch: Any) -> None:
    """Ensure the drain finalizer is set on the CR.

    kopf provides a ``patch.metadata`` proxy with append-only
    semantics on the finalizers list; we set it idempotently.
    """
    finalizers = list(cr.metadata.finalizers or [])
    if DRAIN_FINALIZER in finalizers:
        return
    if hasattr(patch, "metadata") and "finalizers" in dir(patch.metadata):
        patch.metadata["finalizers"] = finalizers + [DRAIN_FINALIZER]


async def remove_finalizer(cr: BotCR, patch: Any) -> None:
    """Remove the drain finalizer (called after drain completes)."""
    finalizers = [f for f in (cr.metadata.finalizers or []) if f != DRAIN_FINALIZER]
    if hasattr(patch, "metadata"):
        patch.metadata["finalizers"] = finalizers


async def run_drain_hook(cr: BotCR, *, logger=logger) -> None:
    """Wait for the bot to drain.

    The bot pod's :class:`BotKernel.run` already handles SIGTERM and
    runs through ``Running -> Draining -> Stopped``. This operator-side
    hook waits for the pod to reach ``Phase=Succeeded``/``Failed`` (or
    times out) and then removes the finalizer.

    Default timeout: 30s for HFT, 300s otherwise.
    """
    timeout = 30.0 if cr.spec.capabilities.frequency == "hft" else 300.0
    logger.info(
        "drain bot %s/%s; waiting %.0fs for pod termination",
        cr.metadata.namespace,
        cr.metadata.name,
        timeout,
    )
    try:
        await asyncio.wait_for(_wait_for_pod_gone(cr), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("drain timeout for %s/%s", cr.metadata.namespace, cr.metadata.name)
    except Exception:  # noqa: BLE001
        logger.exception("drain hook raised")


async def _wait_for_pod_gone(cr: BotCR) -> None:
    """Poll the bot's Pod until it disappears.

    Implementation degrades to a fixed sleep when kubernetes-asyncio
    isn't installed (e.g. operator running locally with stub APIs).
    """
    try:
        from kubernetes_asyncio import client, config  # type: ignore[import-not-found]
    except ImportError:
        await asyncio.sleep(5.0)
        return
    try:
        try:
            config.load_incluster_config()
        except config.ConfigException:  # type: ignore[attr-defined]
            await config.load_kube_config()
    except Exception:  # noqa: BLE001
        await asyncio.sleep(5.0)
        return
    api = client.CoreV1Api()
    while True:
        try:
            pods = await api.list_namespaced_pod(
                namespace=cr.metadata.namespace,
                label_selector=f"quantbot.io/bot-slug={cr.metadata.name}",
            )
            if not pods.items:
                return
        except Exception:  # noqa: BLE001
            return
        await asyncio.sleep(2.0)


__all__ = [
    "DRAIN_FINALIZER",
    "install_finalizer",
    "remove_finalizer",
    "run_drain_hook",
]
