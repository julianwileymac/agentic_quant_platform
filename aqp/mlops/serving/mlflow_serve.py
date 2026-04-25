"""MLflow Models serving adapter.

Wraps ``mlflow models serve`` so any model logged with ``mlflow.log_model``
(in any flavor — sklearn, pytorch, xgboost, pyfunc) can be spawned behind
a local HTTP endpoint that speaks the MLflow inference spec.

Registry / run URIs are passed through unchanged; filesystem paths are
supported as well.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

from aqp.config import settings
from aqp.core.registry import serving
from aqp.mlops.serving.base import (
    DeploymentInfo,
    ModelDeployment,
    PreparedModel,
    _spawn,
)

logger = logging.getLogger(__name__)


@serving("MLflowServe")
class MLflowServeDeployment(ModelDeployment):
    """Launch ``mlflow models serve -m <uri>`` as a subprocess."""

    backend_name = "mlflow-serve"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        workers: int = 1,
        enable_mlserver: bool = False,
        env_manager: str = "local",
    ) -> None:
        self.host = host or settings.mlflow_serve_host
        self.port = int(port or settings.mlflow_serve_port)
        self.workers = int(workers)
        self.enable_mlserver = bool(enable_mlserver)
        self.env_manager = env_manager  # local | virtualenv | conda
        self._proc: subprocess.Popen[str] | None = None

    def deploy(self, model: PreparedModel, **kwargs: Any) -> DeploymentInfo:
        host = kwargs.get("host", self.host)
        port = int(kwargs.get("port", self.port))
        argv = [
            "mlflow",
            "models",
            "serve",
            "-m",
            model.model_uri,
            "--host",
            str(host),
            "--port",
            str(port),
            "--workers",
            str(self.workers),
            "--env-manager",
            self.env_manager,
        ]
        if self.enable_mlserver:
            argv.append("--enable-mlserver")

        env = {"MLFLOW_TRACKING_URI": settings.mlflow_tracking_uri}
        self._proc = _spawn(argv, env=env)

        # Give the model server a moment to bind before we return.
        time.sleep(1.0)

        info = DeploymentInfo(
            backend=self.backend_name,
            endpoint_url=f"http://{host}:{port}",
            pid=self._proc.pid,
            process_name="mlflow-models-serve",
            model_uri=model.model_uri,
            metadata={"workers": self.workers, "enable_mlserver": self.enable_mlserver},
        )
        logger.info("mlflow serve up at %s (pid=%s)", info.endpoint_url, info.pid)
        return info

    def stop(self, info: DeploymentInfo) -> bool:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return True
        try:
            proc.terminate()
            try:
                proc.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                proc.kill()
            return True
        except Exception:
            logger.exception("failed to stop mlflow serve")
            return False


__all__ = ["MLflowServeDeployment"]
