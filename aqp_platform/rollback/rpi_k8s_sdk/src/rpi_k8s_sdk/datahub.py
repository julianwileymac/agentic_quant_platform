"""DataHub metadata helpers for the Kubernetes catalog."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .access import LocalAccessSettings, load_settings


@dataclass(frozen=True, slots=True)
class DataHubRecipe:
    source_type: str
    source_config: dict[str, Any]
    server: str
    token: str = ""

    def as_dict(self) -> dict[str, Any]:
        sink_config: dict[str, Any] = {"server": self.server}
        if self.token:
            sink_config["token"] = self.token
        return {
            "source": {"type": self.source_type, "config": self.source_config},
            "sink": {"type": "datahub-rest", "config": sink_config},
        }


class DataHubClient:
    """Client-side bridge for DataHub GMS and ingestion recipes."""

    def __init__(self, settings: LocalAccessSettings | None = None):
        self.settings = settings or load_settings()

    def emitter(self) -> Any:
        try:
            from datahub.emitter.rest_emitter import DataHubRestEmitter
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("Install rpi_k8s_sdk[datahub] to use DataHub helpers") from exc
        return DataHubRestEmitter(gms_server=self.settings.datahub_gms_url, token=self.settings.datahub_token or None)

    def recipe(self, source_type: str, source_config: dict[str, Any]) -> DataHubRecipe:
        return DataHubRecipe(
            source_type=source_type,
            source_config=source_config,
            server=self.settings.datahub_gms_url,
            token=self.settings.datahub_token,
        )

    def minio_recipe(self, *, buckets: list[str] | None = None) -> DataHubRecipe:
        path_specs = [{"include": f"s3://{bucket}/**"} for bucket in (buckets or ["mlflow-artifacts", "iceberg-warehouse", "pipeline-raw", "pipeline-processed"])]
        return self.recipe(
            "s3",
            {
                "path_specs": path_specs,
                "aws_config": {
                    "aws_access_key_id": self.settings.minio_access_key,
                    "aws_secret_access_key": self.settings.minio_secret_key,
                    "aws_endpoint_url": self.settings.minio_endpoint,
                    "aws_region": self.settings.minio_region,
                },
                "profiling": {"enabled": False},
                "stateful_ingestion": {"enabled": True, "remove_stale_metadata": True},
            },
        )

    def mlflow_recipe(self) -> DataHubRecipe:
        return self.recipe("mlflow", {"tracking_uri": self.settings.mlflow_tracking_uri})

    def run_recipe(self, recipe: DataHubRecipe, *, config_path: str | Path | None = None) -> subprocess.CompletedProcess[str]:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("Install rpi_k8s_sdk[datahub] to run ingestion recipes") from exc

        if config_path:
            path = Path(config_path)
            path.write_text(yaml.safe_dump(recipe.as_dict(), sort_keys=False), encoding="utf-8")
            return subprocess.run(["datahub", "ingest", "-c", str(path)], check=True, capture_output=True, text=True)

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as handle:
            yaml.safe_dump(recipe.as_dict(), handle, sort_keys=False)
            path = Path(handle.name)
        try:
            return subprocess.run(["datahub", "ingest", "-c", str(path)], check=True, capture_output=True, text=True)
        finally:
            path.unlink(missing_ok=True)
