"""Flink management service.

Surfaces the Flink Kubernetes Operator CRDs (``FlinkDeployment``,
``FlinkSessionJob``) and the Flink REST API (via the in-cluster
``flink-trading-session-rest`` service) as a single control plane.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from kubernetes.client.exceptions import ApiException

from ..config import Settings
from ..models.flink import (
    FlinkDeploymentInfo,
    FlinkJobState,
    FlinkMetrics,
    FlinkSessionJobCreate,
    FlinkSessionJobInfo,
    FlinkSessionJobPatch,
)
from ..telemetry.tracing import traced
from .kubernetes_service import KubernetesService

logger = logging.getLogger(__name__)

FLINK_GROUP = "flink.apache.org"
FLINK_VERSION = "v1beta1"


class FlinkService:
    """Flink control plane (operator CRDs + REST API)."""

    def __init__(self, settings: Settings, k8s_service: KubernetesService) -> None:
        self.settings = settings
        self.k8s = k8s_service

    # ------------------------------------------------------------------
    # FlinkDeployment (session cluster)
    # ------------------------------------------------------------------

    @traced("flink.list_deployments")
    async def list_deployments(self) -> List[FlinkDeploymentInfo]:
        try:
            res = self.k8s.custom_api.list_namespaced_custom_object(
                group=FLINK_GROUP,
                version=FLINK_VERSION,
                namespace=self.settings.flink.namespace,
                plural="flinkdeployments",
            )
            return [self._deployment_from_item(i) for i in res.get("items", [])]
        except ApiException as exc:
            logger.warning("list flinkdeployments failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # FlinkSessionJob
    # ------------------------------------------------------------------

    @traced("flink.list_session_jobs")
    async def list_session_jobs(self) -> List[FlinkSessionJobInfo]:
        try:
            res = self.k8s.custom_api.list_namespaced_custom_object(
                group=FLINK_GROUP,
                version=FLINK_VERSION,
                namespace=self.settings.flink.namespace,
                plural="flinksessionjobs",
            )
            return [self._session_job_from_item(i) for i in res.get("items", [])]
        except ApiException as exc:
            logger.warning("list flinksessionjobs failed: %s", exc)
            return []

    @traced("flink.get_session_job")
    async def get_session_job(self, name: str) -> Optional[FlinkSessionJobInfo]:
        try:
            item = self.k8s.custom_api.get_namespaced_custom_object(
                group=FLINK_GROUP,
                version=FLINK_VERSION,
                namespace=self.settings.flink.namespace,
                plural="flinksessionjobs",
                name=name,
            )
            return self._session_job_from_item(item)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    @traced("flink.create_session_job")
    async def create_session_job(self, payload: FlinkSessionJobCreate) -> FlinkSessionJobInfo:
        body = {
            "apiVersion": f"{FLINK_GROUP}/{FLINK_VERSION}",
            "kind": "FlinkSessionJob",
            "metadata": {
                "name": payload.name,
                "namespace": self.settings.flink.namespace,
                "labels": {
                    "app": payload.deployment,
                    "job": payload.name,
                },
            },
            "spec": {
                "deploymentName": payload.deployment,
                "job": {
                    "jarURI": payload.jar_uri,
                    "entryClass": payload.entry_class,
                    "args": payload.args,
                    "parallelism": payload.parallelism,
                    "upgradeMode": payload.upgrade_mode,
                    "state": payload.state.value,
                },
            },
        }
        item = self.k8s.custom_api.create_namespaced_custom_object(
            group=FLINK_GROUP,
            version=FLINK_VERSION,
            namespace=self.settings.flink.namespace,
            plural="flinksessionjobs",
            body=body,
        )
        return self._session_job_from_item(item)

    @traced("flink.patch_session_job")
    async def patch_session_job(self, name: str, patch: FlinkSessionJobPatch) -> FlinkSessionJobInfo:
        ops: List[Dict[str, Any]] = []
        if patch.state is not None:
            ops.append({"op": "replace", "path": "/spec/job/state", "value": patch.state.value})
        if patch.parallelism is not None:
            ops.append({"op": "replace", "path": "/spec/job/parallelism", "value": patch.parallelism})
        if patch.upgrade_mode is not None:
            ops.append({"op": "replace", "path": "/spec/job/upgradeMode", "value": patch.upgrade_mode})
        if ops:
            self.k8s.custom_api.patch_namespaced_custom_object(
                group=FLINK_GROUP,
                version=FLINK_VERSION,
                namespace=self.settings.flink.namespace,
                plural="flinksessionjobs",
                name=name,
                body=ops,
                _content_type="application/json-patch+json",
            )
        if patch.savepoint_trigger:
            self.k8s.custom_api.patch_namespaced_custom_object(
                group=FLINK_GROUP,
                version=FLINK_VERSION,
                namespace=self.settings.flink.namespace,
                plural="flinksessionjobs",
                name=name,
                body={
                    "metadata": {
                        "annotations": {
                            "flink.apache.org/savepointTriggerNonce": str(int(datetime.utcnow().timestamp())),
                        }
                    }
                },
            )
        current = await self.get_session_job(name)
        if current is None:
            raise RuntimeError(f"FlinkSessionJob {name} not found after patch")
        return current

    @traced("flink.delete_session_job")
    async def delete_session_job(self, name: str) -> None:
        try:
            self.k8s.custom_api.delete_namespaced_custom_object(
                group=FLINK_GROUP,
                version=FLINK_VERSION,
                namespace=self.settings.flink.namespace,
                plural="flinksessionjobs",
                name=name,
            )
        except ApiException as exc:
            if exc.status != 404:
                raise

    # ------------------------------------------------------------------
    # Flink REST API
    # ------------------------------------------------------------------

    @traced("flink.list_jobs_rest")
    async def list_rest_jobs(self) -> List[FlinkMetrics]:
        if not self.settings.flink.rest_url:
            return []
        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.get(f"{self.settings.flink.rest_url}/jobs/overview")
            res.raise_for_status()
            data = res.json()
            metrics = []
            for job in data.get("jobs", []):
                metrics.append(
                    FlinkMetrics(
                        job_id=job.get("jid", ""),
                        name=job.get("name", ""),
                        state=job.get("state", "UNKNOWN"),
                        start_time=job.get("start-time"),
                        duration_ms=job.get("duration"),
                        records_in=None,
                        records_out=None,
                    )
                )
            return metrics

    @traced("flink.get_job_metrics_rest")
    async def get_job_metrics(self, job_id: str) -> FlinkMetrics:
        async with httpx.AsyncClient(timeout=10.0) as http:
            detail = await http.get(f"{self.settings.flink.rest_url}/jobs/{job_id}")
            detail.raise_for_status()
            body = detail.json()
            vertices = body.get("vertices") or []
            records_in = sum(v.get("metrics", {}).get("read-records", 0) for v in vertices)
            records_out = sum(v.get("metrics", {}).get("write-records", 0) for v in vertices)
            checkpoints = None
            try:
                cp = await http.get(f"{self.settings.flink.rest_url}/jobs/{job_id}/checkpoints")
                checkpoints = cp.json() if cp.status_code < 400 else None
            except httpx.HTTPError:
                pass
            return FlinkMetrics(
                job_id=body.get("jid", job_id),
                name=body.get("name", ""),
                state=body.get("state", "UNKNOWN"),
                start_time=body.get("start-time"),
                duration_ms=body.get("duration"),
                records_in=records_in,
                records_out=records_out,
                checkpoints=checkpoints,
            )

    # ------------------------------------------------------------------
    # Transformers
    # ------------------------------------------------------------------

    def _deployment_from_item(self, item: Dict[str, Any]) -> FlinkDeploymentInfo:
        meta = item.get("metadata") or {}
        spec = item.get("spec") or {}
        status = item.get("status") or {}
        return FlinkDeploymentInfo(
            name=meta.get("name", "?"),
            namespace=meta.get("namespace", self.settings.flink.namespace),
            image=spec.get("image", ""),
            flink_version=spec.get("flinkVersion", ""),
            task_manager_replicas=int((spec.get("taskManager") or {}).get("replicas", 0)),
            lifecycle_state=status.get("lifecycleState"),
            status=status,
            created_at=_parse_datetime(meta.get("creationTimestamp")),
        )

    def _session_job_from_item(self, item: Dict[str, Any]) -> FlinkSessionJobInfo:
        meta = item.get("metadata") or {}
        spec = item.get("spec") or {}
        job = spec.get("job") or {}
        status = item.get("status") or {}
        job_status = status.get("jobStatus") or {}
        state_str = str(job.get("state", "suspended")).lower()
        try:
            state = FlinkJobState(state_str)
        except ValueError:
            state = FlinkJobState.UNKNOWN
        savepoint = None
        info = job_status.get("savepointInfo") or {}
        if isinstance(info, dict):
            savepoint = info.get("lastSavepoint")
        return FlinkSessionJobInfo(
            name=meta.get("name", "?"),
            namespace=meta.get("namespace", self.settings.flink.namespace),
            deployment=spec.get("deploymentName", ""),
            jar_uri=job.get("jarURI", ""),
            entry_class=job.get("entryClass"),
            state=state,
            parallelism=int(job.get("parallelism", 1)),
            upgrade_mode=job.get("upgradeMode"),
            job_status=job_status,
            savepoint_path=savepoint.get("location") if isinstance(savepoint, dict) else None,
            created_at=_parse_datetime(meta.get("creationTimestamp")),
        )


def _parse_datetime(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
