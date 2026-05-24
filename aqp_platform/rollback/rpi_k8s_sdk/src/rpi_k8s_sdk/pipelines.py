"""Local controls for Argo-backed ingestion pipelines."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .access import LocalAccessSettings, load_settings


@dataclass(frozen=True, slots=True)
class PipelineRun:
    namespace: str
    name: str
    status: str | None = None
    parameters: dict[str, str] = field(default_factory=dict)

    @property
    def argo_ui_path(self) -> str:
        return f"/workflows/{self.namespace}/{self.name}"


class ArgoPipelineClient:
    """Submit and inspect Argo WorkflowTemplate runs through Kubernetes CRDs."""

    group = "argoproj.io"
    version = "v1alpha1"
    plural = "workflows"

    def __init__(self, settings: LocalAccessSettings | None = None, custom_api: Any | None = None):
        self.settings = settings or load_settings()
        self._custom_api = custom_api

    @property
    def custom_api(self) -> Any:
        if self._custom_api is None:
            try:
                from kubernetes import client, config
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise RuntimeError("Install rpi_k8s_sdk[kubernetes] to use pipeline controls") from exc
            if self.settings.kubeconfig:
                config.load_kube_config(
                    config_file=self.settings.kubeconfig,
                    context=self.settings.kube_context or None,
                )
            else:
                config.load_kube_config(context=self.settings.kube_context or None)
            self._custom_api = client.CustomObjectsApi()
        return self._custom_api

    def submit_template(
        self,
        template_name: str,
        *,
        name: str,
        parameters: dict[str, str],
        namespace: str | None = None,
    ) -> PipelineRun:
        target_namespace = namespace or self.settings.namespace_mlops
        body = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {"generateName": f"{name}-", "namespace": target_namespace},
            "spec": {
                "workflowTemplateRef": {"name": template_name},
                "arguments": {
                    "parameters": [{"name": key, "value": value} for key, value in parameters.items()]
                },
            },
        }
        created = self.custom_api.create_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=target_namespace,
            plural=self.plural,
            body=body,
        )
        return PipelineRun(
            namespace=target_namespace,
            name=created["metadata"]["name"],
            status=created.get("status", {}).get("phase"),
            parameters=parameters,
        )

    def raw_ingest(
        self,
        *,
        source_name: str,
        source_uri: str,
        source_type: str = "http",
        output_prefix: str = "raw",
        target_bucket: str = "pipeline-raw",
        namespace: str | None = None,
    ) -> PipelineRun:
        return self.submit_template(
            "pipeline-raw-ingest",
            name=f"raw-ingest-{source_name}",
            namespace=namespace,
            parameters={
                "source_type": source_type,
                "source_name": source_name,
                "source_uri": source_uri,
                "output_prefix": output_prefix,
                "target_bucket": target_bucket,
            },
        )

    def get_run(self, name: str, *, namespace: str | None = None) -> PipelineRun:
        target_namespace = namespace or self.settings.namespace_mlops
        obj = self.custom_api.get_namespaced_custom_object(
            group=self.group,
            version=self.version,
            namespace=target_namespace,
            plural=self.plural,
            name=name,
        )
        return PipelineRun(
            namespace=target_namespace,
            name=name,
            status=obj.get("status", {}).get("phase"),
            parameters={
                item.get("name", ""): item.get("value", "")
                for item in obj.get("spec", {}).get("arguments", {}).get("parameters", [])
                if item.get("name")
            },
        )

    def wait_for_run(
        self,
        name: str,
        *,
        namespace: str | None = None,
        timeout_seconds: float = 600,
        poll_seconds: float = 5,
    ) -> PipelineRun:
        deadline = time.monotonic() + timeout_seconds
        while True:
            run = self.get_run(name, namespace=namespace)
            if run.status in {"Succeeded", "Failed", "Error"}:
                return run
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for workflow {run.namespace}/{run.name}")
            time.sleep(poll_seconds)
