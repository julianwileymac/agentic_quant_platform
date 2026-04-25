"""Shared contracts for model-serving backends.

Every serving backend (MLflow Serve, Ray Serve, TorchServe) accepts a
model reference — a filesystem path, an MLflow registry URI
(``models:/<name>/<stage>``), or a tracking URI
(``runs:/<run-id>/<artifact>``) — and exposes a stable HTTP endpoint.

The :class:`ModelDeployment` protocol is intentionally narrow so adapters
can share a CLI, a JSON health-check, and the same OTel spans.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


_MLFLOW_URI_RE = re.compile(r"^(?:models:|runs:|mlflow-artifacts:|s3:|minio:)")


@dataclass
class PreparedModel:
    """A resolved model reference ready for a serving backend.

    ``local_path`` is populated when the backend needs filesystem access
    (TorchServe .mar packaging, Ray Serve pickle load). ``model_uri`` is
    preserved so MLflow Serve can point directly at the registry.
    """

    model_uri: str
    local_path: Path | None = None
    flavor: str | None = None  # "sklearn" | "pytorch" | "xgboost" | ...
    run_id: str | None = None
    name: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_mlflow_uri(self) -> bool:
        return bool(_MLFLOW_URI_RE.match(self.model_uri))


@dataclass
class DeploymentInfo:
    """Runtime handle returned by :meth:`ModelDeployment.deploy`."""

    backend: str
    endpoint_url: str
    pid: int | None = None
    process_name: str | None = None
    model_uri: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ModelDeployment(ABC):
    """Protocol implemented by every serving-backend adapter."""

    backend_name: str = "base"

    @abstractmethod
    def deploy(self, model: PreparedModel, **kwargs: Any) -> DeploymentInfo:
        """Launch a serving process for ``model`` and return its handle."""

    @abstractmethod
    def stop(self, info: DeploymentInfo) -> bool:
        """Terminate a previously-launched deployment. Returns True on success."""

    def health_check(self, info: DeploymentInfo) -> bool:
        """Default health check — assumes ``endpoint_url`` is reachable."""
        try:
            import httpx

            with httpx.Client(timeout=5.0) as client:
                for path in ("/ping", "/health", "/v1/models", "/"):
                    try:
                        r = client.get(info.endpoint_url.rstrip("/") + path)
                        if r.status_code < 500:
                            return True
                    except Exception:
                        continue
            return False
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Internal helpers reused by all backends.
# ---------------------------------------------------------------------------


def resolve_model(model_uri: str, download_dir: str | Path | None = None) -> PreparedModel:
    """Resolve an MLflow / filesystem URI into a :class:`PreparedModel`.

    For filesystem paths the ``local_path`` is the path itself. For MLflow
    registry / run URIs we call ``mlflow.artifacts.download_artifacts`` so
    backends that need local files can proceed.
    """
    if _MLFLOW_URI_RE.match(model_uri):
        try:
            import mlflow
            from aqp.config import settings

            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            local = None
            if download_dir is not None:
                local = Path(mlflow.artifacts.download_artifacts(model_uri, dst_path=str(download_dir)))
            else:
                local = Path(mlflow.artifacts.download_artifacts(model_uri))
            return PreparedModel(model_uri=model_uri, local_path=local)
        except Exception:
            logger.exception("resolve_model: MLflow download failed for %s", model_uri)
            return PreparedModel(model_uri=model_uri, local_path=None)

    p = Path(model_uri).expanduser()
    return PreparedModel(model_uri=str(p), local_path=p if p.exists() else None)


def _spawn(argv: list[str], env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    """Launch a detached serving process capturing stdout/stderr."""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    logger.info("spawn: %s", " ".join(argv))
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=merged_env,
        text=True,
    )

    def _drain() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                logger.debug("%s | %s", argv[0], line.rstrip())
        except Exception:
            logger.debug("_drain exit", exc_info=True)

    threading.Thread(target=_drain, daemon=True).start()
    return proc


__all__ = [
    "DeploymentInfo",
    "ModelDeployment",
    "PreparedModel",
    "_spawn",
    "resolve_model",
]
