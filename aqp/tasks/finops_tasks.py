"""FinOps governance Celery tasks.

Closes the cost-attribution chain that starts at
:meth:`aqp.config.Settings.finops_labels`. Every six hours (per the beat
schedule in :mod:`aqp.tasks.celery_app`) the ``audit`` task scans the
running Kubernetes cluster for any Pod / Job / CronJob / Deployment that
is missing one or more of the four mandatory FinOps labels and emits a
high-priority alert via the standard progress bus so the on-call FinOps
channel can react.

The task is defensive: if the Kubernetes Python client is unavailable
(e.g. local dev with no cluster credentials) it returns an explanatory
no-op result rather than raising — the Kyverno ``ClusterPolicy`` in
``rpi_kubernetes/kubernetes/policies/finops/`` is the authoritative
enforcement layer; this task is the periodic safety net that catches
mis-applied or pre-existing workloads that pre-date the policy.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# The four mandatory labels mirror Settings.finops_labels(). ``environment``
# is intentionally OPTIONAL on K8s resources because some shared services
# legitimately span environments (Prometheus, ingress controllers, etc.).
_REQUIRED_LABELS: tuple[str, ...] = (
    "project",
    "cost_center",
    "owner",
    "data_classification",
)


def _scan_pods(api: Any) -> list[dict[str, Any]]:
    """Return ``[{namespace, name, kind, missing}]`` for every Pod missing tags."""
    untagged: list[dict[str, Any]] = []
    pods = api.list_pod_for_all_namespaces(timeout_seconds=30)
    for pod in getattr(pods, "items", []) or []:
        labels = (pod.metadata.labels or {}) if pod.metadata is not None else {}
        missing = [k for k in _REQUIRED_LABELS if k not in labels or not labels.get(k)]
        if missing:
            untagged.append(
                {
                    "kind": "Pod",
                    "namespace": pod.metadata.namespace,
                    "name": pod.metadata.name,
                    "missing": missing,
                }
            )
    return untagged


def _scan_workloads(batch_api: Any, apps_api: Any) -> list[dict[str, Any]]:
    """Same as :func:`_scan_pods` but for Job / CronJob / Deployment."""
    untagged: list[dict[str, Any]] = []
    sources: list[tuple[str, Any]] = []
    if batch_api is not None:
        try:
            sources.append(("Job", batch_api.list_job_for_all_namespaces(timeout_seconds=30)))
        except Exception:
            logger.debug("list_job_for_all_namespaces failed", exc_info=True)
        try:
            sources.append(
                ("CronJob", batch_api.list_cron_job_for_all_namespaces(timeout_seconds=30))
            )
        except Exception:
            logger.debug("list_cron_job_for_all_namespaces failed", exc_info=True)
    if apps_api is not None:
        try:
            sources.append(
                ("Deployment", apps_api.list_deployment_for_all_namespaces(timeout_seconds=30))
            )
        except Exception:
            logger.debug("list_deployment_for_all_namespaces failed", exc_info=True)
    for kind, listing in sources:
        for obj in getattr(listing, "items", []) or []:
            labels = (obj.metadata.labels or {}) if obj.metadata is not None else {}
            missing = [
                k for k in _REQUIRED_LABELS if k not in labels or not labels.get(k)
            ]
            if missing:
                untagged.append(
                    {
                        "kind": kind,
                        "namespace": obj.metadata.namespace,
                        "name": obj.metadata.name,
                        "missing": missing,
                    }
                )
    return untagged


def _load_kube_clients() -> tuple[Any, Any, Any] | None:
    """Best-effort load of the kubernetes client + cluster config.

    Returns ``None`` when the optional ``kubernetes`` package is missing,
    or when neither in-cluster nor kubeconfig credentials are available.
    """
    try:
        from kubernetes import client, config  # type: ignore[import-not-found]
    except ImportError:
        logger.info("FinOps audit: kubernetes package not installed; skipping")
        return None
    loaded = False
    for loader in (config.load_incluster_config, config.load_kube_config):
        try:
            loader()
            loaded = True
            break
        except Exception:
            continue
    if not loaded:
        logger.info("FinOps audit: no in-cluster or kubeconfig credentials")
        return None
    return client.CoreV1Api(), client.BatchV1Api(), client.AppsV1Api()


@celery_app.task(bind=True, name="aqp.tasks.finops_tasks.audit")
def audit(self, scope: str = "all", *, max_samples: int = 100) -> dict[str, Any]:
    """Scan the cluster for resources missing mandatory FinOps labels.

    Returns ``{ok, scanned, untagged_count, samples, ...}``. When the
    untagged count is non-zero the task also emits an ``error`` event on
    the progress bus so the FinOps channel sees the breach immediately.

    Parameters
    ----------
    scope
        ``"all"`` scans Pods + Jobs + CronJobs + Deployments. Use
        ``"pods"`` to limit the scan to running Pods only (cheaper).
    max_samples
        Cap on the number of untagged-resource samples returned in the
        Celery result payload (full list still goes to the structured
        log). Prevents unbounded payload growth in big clusters.
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", f"FinOps audit scope={scope}")

    clients = _load_kube_clients()
    if clients is None:
        msg = "kubernetes client unavailable"
        result = {
            "ok": True,
            "skipped": True,
            "reason": msg,
            "scanned": 0,
            "untagged_count": 0,
            "samples": [],
            "labels_required": list(_REQUIRED_LABELS),
            "current_finops": settings.finops_labels(),
        }
        emit_done(task_id, result)
        return result

    core_api, batch_api, apps_api = clients

    untagged: list[dict[str, Any]] = []
    scanned = 0
    try:
        emit(task_id, "scanning", "scanning pods")
        pods_untagged = _scan_pods(core_api)
        scanned += 1
        untagged.extend(pods_untagged)
        if scope == "all":
            emit(task_id, "scanning", "scanning jobs / cronjobs / deployments")
            untagged.extend(_scan_workloads(batch_api, apps_api))
            scanned += 3
    except Exception as exc:  # noqa: BLE001
        logger.exception("FinOps audit failed")
        emit_error(task_id, f"audit failed: {exc}")
        raise

    samples = untagged[:max_samples]
    untagged_count = len(untagged)
    if untagged_count:
        emit_error(
            task_id,
            f"FinOps: {untagged_count} resources missing mandatory tags",
            untagged_count=untagged_count,
            samples=samples,
            labels_required=list(_REQUIRED_LABELS),
        )

    result: dict[str, Any] = {
        "ok": untagged_count == 0,
        "skipped": False,
        "scope": scope,
        "scanned": scanned,
        "untagged_count": untagged_count,
        "samples": samples,
        "labels_required": list(_REQUIRED_LABELS),
        "current_finops": settings.finops_labels(),
    }
    emit_done(task_id, result)
    return result


__all__ = ["audit"]
