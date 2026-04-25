"""Ray Serve deployment adapter.

Loads any AQP ``Model`` pickle or MLflow model URI and exposes it behind a
Ray Serve HTTP endpoint. Callers that already have a running Ray cluster
pass ``ray_address`` (or rely on ``settings.ray_address``); ``auto`` spins
up a local head on the first call.

When Ray is not installed the adapter falls back to a no-op that raises at
:meth:`deploy` so import of :mod:`aqp.mlops.serving` stays cheap.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings
from aqp.core.registry import serving
from aqp.mlops.serving.base import (
    DeploymentInfo,
    ModelDeployment,
    PreparedModel,
)

logger = logging.getLogger(__name__)


class _AqpRayDeployment:
    """Ray Serve deployment class (built lazily — needs ``ray[serve]``).

    The body is defined inside :meth:`RayServeDeployment.deploy` because
    ``@serve.deployment`` must be applied at runtime, not at import time.
    """


@serving("RayServe")
class RayServeDeployment(ModelDeployment):
    backend_name = "ray-serve"

    def __init__(
        self,
        ray_address: str | None = None,
        route_prefix: str | None = None,
        name: str = "aqp-model",
        http_host: str | None = None,
        http_port: int | None = None,
        num_replicas: int = 1,
        ray_actor_options: dict[str, Any] | None = None,
    ) -> None:
        self.ray_address = ray_address or settings.ray_address
        self.route_prefix = route_prefix or settings.ray_serve_route_prefix
        self.name = name
        self.http_host = http_host or settings.ray_serve_http_host
        self.http_port = int(http_port or settings.ray_serve_http_port)
        self.num_replicas = int(num_replicas)
        self.ray_actor_options = ray_actor_options or {}
        self._handle: Any | None = None

    # ------------------------------------------------------------------

    def deploy(self, model: PreparedModel, **kwargs: Any) -> DeploymentInfo:
        try:
            import ray
            from ray import serve
        except Exception as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "Ray Serve is not available. Install with `pip install aqp[serving-ray]`"
            ) from exc

        if not ray.is_initialized():
            init_kwargs: dict[str, Any] = {"ignore_reinit_error": True}
            if self.ray_address and self.ray_address != "auto":
                init_kwargs["address"] = self.ray_address
            ray.init(**init_kwargs)

        serve.start(
            http_options={"host": self.http_host, "port": self.http_port},
            detached=True,
        )

        route_prefix = kwargs.get("route_prefix", self.route_prefix)
        name = kwargs.get("name", self.name)
        num_replicas = int(kwargs.get("num_replicas", self.num_replicas))
        actor_options = {**self.ray_actor_options, **kwargs.get("ray_actor_options", {})}

        model_uri = model.model_uri
        local_path = str(model.local_path) if model.local_path else None
        is_mlflow = model.is_mlflow_uri

        @serve.deployment(
            name=name,
            num_replicas=num_replicas,
            ray_actor_options=actor_options,
        )
        class _Deployment:
            def __init__(self) -> None:
                self.model = self._load()

            @staticmethod
            def _load() -> Any:
                if is_mlflow:
                    import mlflow

                    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
                    return mlflow.pyfunc.load_model(model_uri)

                import pickle
                from pathlib import Path

                path = Path(local_path) if local_path else Path(model_uri)
                with open(path, "rb") as fh:
                    return pickle.load(fh)

            async def __call__(self, request: Any) -> Any:
                payload = await request.json() if hasattr(request, "json") else request
                if isinstance(payload, list):
                    import pandas as pd

                    df = pd.DataFrame(payload)
                    return self.model.predict(df).tolist() if hasattr(self.model, "predict") else []
                if isinstance(payload, dict) and "dataframe_records" in payload:
                    import pandas as pd

                    df = pd.DataFrame(payload["dataframe_records"])
                    return self.model.predict(df).tolist() if hasattr(self.model, "predict") else []
                return {"error": "unsupported payload shape"}

        app = _Deployment.bind()
        serve.run(app, name=name, route_prefix=route_prefix)

        endpoint = f"http://{self.http_host}:{self.http_port}{route_prefix}"
        info = DeploymentInfo(
            backend=self.backend_name,
            endpoint_url=endpoint,
            process_name="ray-serve",
            model_uri=model_uri,
            metadata={
                "num_replicas": num_replicas,
                "ray_address": self.ray_address,
                "route_prefix": route_prefix,
                "name": name,
            },
        )
        self._handle = {"name": name}
        logger.info("Ray Serve deployment %s bound at %s", name, endpoint)
        return info

    def stop(self, info: DeploymentInfo) -> bool:
        try:
            from ray import serve

            name = info.metadata.get("name", self.name)
            try:
                serve.delete(name)
            except Exception:
                # Older Ray API fallback
                serve.shutdown()
            return True
        except Exception:
            logger.exception("ray serve stop failed")
            return False


__all__ = ["RayServeDeployment"]
