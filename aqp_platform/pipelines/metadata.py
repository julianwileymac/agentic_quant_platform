"""Optional DataHub metadata emission for pipeline outputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from .config import PipelineConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MetadataAsset:
    platform: str
    name: str
    properties: dict[str, Any]


class DataHubMetadataSink:
    """Best-effort metadata sink; disabled unless configured by env."""

    def __init__(self, config: PipelineConfig):
        self.config = config

    def enabled(self) -> bool:
        return self.config.datahub_enabled

    def emit_dataset(self, asset: MetadataAsset) -> bool:
        if not self.enabled():
            return False
        try:
            from datahub.emitter.mce_builder import make_dataset_urn
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.emitter.rest_emitter import DataHubRestEmitter
            from datahub.metadata.schema_classes import DatasetPropertiesClass
        except ImportError:
            logger.warning("acryl-datahub is not installed; metadata emission skipped")
            return False

        try:
            urn = make_dataset_urn(asset.platform, asset.name, self.config.datahub_env)
            aspect = DatasetPropertiesClass(
                name=asset.name,
                description=asset.properties.get("description"),
                customProperties={key: str(value) for key, value in asset.properties.items()},
            )
            emitter = DataHubRestEmitter(
                gms_server=self.config.datahub_gms_url,
                token=self.config.datahub_token or None,
            )
            emitter.emit(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("DataHub metadata emission failed for %s: %s", asset.name, exc)
            return False


def emit_minio_object(
    config: PipelineConfig,
    *,
    bucket: str,
    key: str,
    properties: dict[str, Any] | None = None,
) -> bool:
    return DataHubMetadataSink(config).emit_dataset(
        MetadataAsset(
            platform="s3",
            name=f"s3://{bucket}/{key}",
            properties={"bucket": bucket, "key": key, **(properties or {})},
        )
    )


def emit_pipeline_run(
    config: PipelineConfig,
    *,
    name: str,
    properties: dict[str, Any] | None = None,
) -> bool:
    return DataHubMetadataSink(config).emit_dataset(
        MetadataAsset(
            platform="rpi-pipeline",
            name=name,
            properties=properties or {},
        )
    )
