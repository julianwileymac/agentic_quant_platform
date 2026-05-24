"""Model download, upload, and serving manifest helpers.

This module is the SDK entry point for the **KServe-first** serving plane
introduced in 2026-Q2 (see ``kubernetes/mlops/bentoml/DEPRECATED.md`` for
context on the Yatai/BentoML retirement).

Typical usage from a notebook or Dagster asset::

    from rpi_k8s_sdk import ModelStore, kserve_inferenceservice_manifest

    store = ModelStore()

    # Pull a model from MLflow registry into the cluster's model bucket.
    artifact = store.from_mlflow_run(run_id="abc123", artifact_path="model")

    # Build the KServe InferenceService manifest and apply it.
    manifest = kserve_inferenceservice_manifest(
        name="my-classifier",
        model_uri=artifact.s3_uri,
        runtime="sklearn",
    )
    store.deploy_to_kserve(manifest)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .access import LocalAccessSettings, load_settings
from .minio import MinioClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    model_id: str
    local_path: Path
    bucket: str
    prefix: str

    @property
    def s3_uri(self) -> str:
        return f"s3://{self.bucket}/{self.prefix.rstrip('/')}/"


class ModelStore:
    """Download models locally and publish them to the cluster model bucket."""

    def __init__(
        self,
        settings: LocalAccessSettings | None = None,
        minio: MinioClient | None = None,
    ):
        self.settings = settings or load_settings()
        self.minio = minio or MinioClient(self.settings)

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def download_hf_snapshot(
        self,
        model_id: str,
        *,
        local_dir: str | Path,
        revision: str | None = None,
    ) -> Path:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Install rpi_k8s_sdk[serving] to download Hugging Face models"
            ) from exc
        return Path(
            snapshot_download(
                repo_id=model_id, revision=revision, local_dir=str(local_dir)
            )
        )

    def from_mlflow_run(
        self,
        *,
        run_id: str,
        artifact_path: str = "model",
        local_dir: str | Path | None = None,
        bucket: str | None = None,
        prefix: str | None = None,
    ) -> ModelArtifact:
        """Pull an MLflow-logged model into the cluster's model bucket.

        Downloads the artifact directory locally via the MLflow client and
        re-uploads it under the agreed-upon ``model-registry`` bucket prefix
        so KServe's storage initializer can pull it via ``s3://``.
        """

        try:
            import tempfile

            from mlflow.tracking import MlflowClient
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "Install rpi_k8s_sdk[mlflow] to copy models from MLflow"
            ) from exc

        client = MlflowClient(tracking_uri=self.settings.mlflow_tracking_uri)
        target_bucket = bucket or self.settings.model_bucket
        target_prefix = prefix or f"mlflow-runs/{run_id}/{artifact_path.strip('/')}"

        if local_dir is None:
            local_dir = Path(tempfile.mkdtemp(prefix=f"mlflow-run-{run_id}-"))
        local_root = Path(local_dir)
        local_root.mkdir(parents=True, exist_ok=True)

        downloaded = client.download_artifacts(
            run_id=run_id, path=artifact_path, dst_path=str(local_root)
        )
        logger.info("MLflow run %s artifacts staged at %s", run_id, downloaded)

        return self.upload_directory(
            model_id=run_id,
            local_dir=Path(downloaded),
            bucket=target_bucket,
            prefix=target_prefix,
        )

    def from_mlflow_registered_model(
        self,
        *,
        name: str,
        version: str | int,
        local_dir: str | Path | None = None,
        bucket: str | None = None,
    ) -> ModelArtifact:
        """Pull a *registered* MLflow model version into the model bucket.

        Convenience wrapper that resolves the registered name + version to
        its underlying run and delegates to :meth:`from_mlflow_run`.
        """

        try:
            from mlflow.tracking import MlflowClient
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Install rpi_k8s_sdk[mlflow] to copy models from MLflow"
            ) from exc

        client = MlflowClient(tracking_uri=self.settings.mlflow_tracking_uri)
        version_str = str(version)
        mv = client.get_model_version(name=name, version=version_str)
        prefix = f"models/{name}/{version_str}"
        return self.from_mlflow_run(
            run_id=mv.run_id,
            artifact_path=mv.source.split("/")[-1] if "/" in mv.source else "model",
            local_dir=local_dir,
            bucket=bucket,
            prefix=prefix,
        )

    # ------------------------------------------------------------------
    # Sinks
    # ------------------------------------------------------------------

    def upload_directory(
        self,
        model_id: str,
        local_dir: str | Path,
        *,
        bucket: str | None = None,
        prefix: str | None = None,
    ) -> ModelArtifact:
        root = Path(local_dir)
        target_bucket = bucket or self.settings.model_bucket
        target_prefix = prefix or model_id.replace("/", "--")
        for path in root.rglob("*"):
            if path.is_file():
                key = f"{target_prefix}/{path.relative_to(root).as_posix()}"
                self.minio.upload_file(target_bucket, key, path)
        return ModelArtifact(
            model_id=model_id,
            local_path=root,
            bucket=target_bucket,
            prefix=target_prefix,
        )

    def deploy_to_kserve(
        self,
        manifest: dict[str, Any],
        *,
        kubeconfig: str | None = None,
        context: str | None = None,
    ) -> dict[str, Any]:
        """Apply a KServe ``InferenceService`` manifest to the cluster.

        Uses ``kubernetes.dynamic`` so any ``apiVersion`` works (handy for
        switching between ``serving.kserve.io/v1beta1`` and ``v1alpha1``).
        Returns the server-side reconciled object so callers can poll
        ``.status``.
        """

        try:
            from kubernetes import client, config
            from kubernetes.dynamic import DynamicClient
        except ImportError as exc:  # pragma: no cover - optional extra
            raise RuntimeError(
                "Install rpi_k8s_sdk[kubernetes] to deploy InferenceServices"
            ) from exc

        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig, context=context)
        else:
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config(context=context)

        api_version = manifest.get("apiVersion", "serving.kserve.io/v1beta1")
        kind = manifest.get("kind", "InferenceService")
        namespace = manifest.get("metadata", {}).get("namespace", "ml-platform")

        dyn = DynamicClient(client.ApiClient())
        resource = dyn.resources.get(api_version=api_version, kind=kind)
        existing = None
        try:
            existing = resource.get(
                name=manifest["metadata"]["name"], namespace=namespace
            )
        except Exception:
            existing = None

        if existing is None:
            applied = resource.create(body=manifest, namespace=namespace)
        else:
            applied = resource.replace(body=manifest, namespace=namespace)

        return applied.to_dict() if hasattr(applied, "to_dict") else dict(applied)


# ---------------------------------------------------------------------------
# Manifest builders.  These return plain dicts so callers can `kubectl apply`
# them via the SDK helpers above or render them to YAML for GitOps.
# ---------------------------------------------------------------------------


def vllm_deployment_manifest(
    *,
    name: str,
    model_uri: str,
    profile: str = "cpu-small",
    namespace: str = "ml-platform",
    replicas: int = 1,
    image: str = "vllm/vllm-openai:v0.6.3",
) -> dict[str, Any]:
    is_gpu = profile in {"gpu", "gpu-x86", "desktop-gpu"}
    resources = (
        {
            "limits": {"nvidia.com/gpu": "1", "cpu": "4", "memory": "24Gi"},
            "requests": {"cpu": "2", "memory": "12Gi"},
        }
        if is_gpu
        else {
            "limits": {"cpu": "4", "memory": "8Gi"},
            "requests": {"cpu": "1", "memory": "2Gi"},
        }
    )
    node_selector = {"kubernetes.io/arch": "amd64"} if is_gpu else {}
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "app": name,
                "app.kubernetes.io/name": name,
                "serving.rpi-k8s.io/runtime": "vllm",
            },
        },
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {
                    "labels": {
                        "app": name,
                        "app.kubernetes.io/name": name,
                    }
                },
                "spec": {
                    "nodeSelector": node_selector,
                    "containers": [
                        {
                            "name": "vllm",
                            "image": image,
                            "args": [
                                "--model",
                                model_uri,
                                "--served-model-name",
                                name,
                            ],
                            "env": [
                                {
                                    "name": "OTEL_EXPORTER_OTLP_ENDPOINT",
                                    "value": "http://otel-collector.observability.svc.cluster.local:4317",
                                },
                                {"name": "OTEL_SERVICE_NAME", "value": name},
                            ],
                            "ports": [{"containerPort": 8000, "name": "http"}],
                            "resources": resources,
                        }
                    ],
                },
            },
        },
    }


def kserve_inferenceservice_manifest(
    *,
    name: str,
    model_uri: str,
    namespace: str = "ml-platform",
    runtime: str = "sklearn",
    min_replicas: int = 1,
    max_replicas: int = 3,
    service_account: str = "model-serving",
) -> dict[str, Any]:
    """Build a minimal ``InferenceService`` for any KServe-supported runtime.

    The default ``sklearn`` runtime is suitable for MLflow-logged models
    (``mlflow.sklearn.log_model(...)``).  Use ``runtime="vllm"`` for LLMs.
    """

    return {
        "apiVersion": "serving.kserve.io/v1beta1",
        "kind": "InferenceService",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "annotations": {
                "serving.kserve.io/deploymentMode": "RawDeployment",
            },
            "labels": {
                "app.kubernetes.io/component": "model-serving",
                "app.kubernetes.io/managed-by": "rpi-k8s-sdk",
                "serving.rpi-k8s.io/source": "sdk",
            },
        },
        "spec": {
            "predictor": {
                "serviceAccountName": service_account,
                "minReplicas": min_replicas,
                "maxReplicas": max_replicas,
                "model": {
                    "modelFormat": {"name": runtime},
                    "storageUri": model_uri,
                    "env": [
                        {
                            "name": "OTEL_EXPORTER_OTLP_ENDPOINT",
                            "value": "http://otel-collector.observability.svc.cluster.local:4317",
                        },
                        {"name": "OTEL_SERVICE_NAME", "value": name},
                    ],
                    "resources": {
                        "requests": {"cpu": "200m", "memory": "512Mi"},
                        "limits": {"cpu": "2", "memory": "4Gi"},
                    },
                },
            }
        },
    }
