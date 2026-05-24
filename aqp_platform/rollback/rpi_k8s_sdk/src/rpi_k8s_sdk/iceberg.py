"""PyIceberg configuration for the DataHub REST catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .access import LocalAccessSettings, load_settings


@dataclass(frozen=True, slots=True)
class IcebergCatalogConfig:
    name: str
    options: dict[str, str]


class IcebergClient:
    """Build and load a PyIceberg catalog backed by DataHub + MinIO."""

    def __init__(self, settings: LocalAccessSettings | None = None, name: str = "rpi"):
        self.settings = settings or load_settings()
        self.name = name

    def config(self) -> IcebergCatalogConfig:
        return IcebergCatalogConfig(
            name=self.name,
            options={
                "type": "rest",
                "uri": self.settings.iceberg_catalog_uri,
                "warehouse": self.settings.iceberg_warehouse,
                "s3.endpoint": self.settings.minio_endpoint,
                "s3.access-key-id": self.settings.minio_access_key,
                "s3.secret-access-key": self.settings.minio_secret_key,
                "s3.region": self.settings.minio_region,
                "s3.path-style-access": "true",
            },
        )

    def load_catalog(self) -> Any:
        try:
            from pyiceberg.catalog import load_catalog
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("Install rpi_k8s_sdk[iceberg] to use Iceberg helpers") from exc
        catalog = self.config()
        return load_catalog(catalog.name, **catalog.options)
