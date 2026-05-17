"""Sink nodes used by manifests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aqp.data.fetchers.sinks.chroma_sink import ChromaSink
from aqp.data.fetchers.sinks.dbt_sink import DbtBuildSink
from aqp.data.fetchers.sinks.iceberg_sink import IcebergSink
from aqp.data.fetchers.sinks.kafka_sink import KafkaSink
from aqp.data.fetchers.sinks.ml_feature_snapshot_sink import MlFeatureSnapshotSink
from aqp.data.fetchers.sinks.parquet_sink import ParquetSink
from aqp.data.fetchers.sinks.profile_sink import ProfileSink


@dataclass(frozen=True)
class SinkKindDescriptor:
    """UI-facing descriptor for a registered sink kind.

    Returned by :func:`list_sink_kinds`. Carries enough metadata for
    the SinkRegistry UI to render a kind picker, default form fields,
    and a default manifest node template.
    """

    kind: str
    display_name: str
    description: str
    config_fields: list[dict[str, Any]] = field(default_factory=list)
    default_node_template: dict[str, Any] = field(default_factory=dict)
    supported_domains: list[str] = field(default_factory=list)
    documentation_url: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "display_name": self.display_name,
            "description": self.description,
            "config_fields": list(self.config_fields),
            "default_node_template": dict(self.default_node_template),
            "supported_domains": list(self.supported_domains),
            "documentation_url": self.documentation_url,
            "tags": list(self.tags),
        }


_SINK_DESCRIPTORS: tuple[SinkKindDescriptor, ...] = (
    SinkKindDescriptor(
        kind="iceberg",
        display_name="Apache Iceberg table",
        description=(
            "Append Arrow batches to a managed Iceberg table via "
            "iceberg_catalog.append_arrow."
        ),
        config_fields=[
            {"name": "namespace", "label": "Namespace", "type": "string", "required": True},
            {"name": "table", "label": "Table", "type": "string", "required": True},
            {
                "name": "mode",
                "label": "Write mode",
                "type": "select",
                "options": ["append", "overwrite"],
                "default": "append",
            },
            {"name": "tags", "label": "Tags", "type": "tags"},
        ],
        default_node_template={"name": "sink.iceberg", "kwargs": {}},
        supported_domains=["bars.*", "fundamentals.*", "reference.*", "user.dataset"],
        tags=["iceberg", "lakehouse"],
    ),
    SinkKindDescriptor(
        kind="parquet",
        display_name="Parquet directory",
        description="Write Arrow batches to a directory of Parquet files.",
        config_fields=[
            {"name": "output_dir", "label": "Output directory", "type": "path", "required": True},
            {"name": "prefix", "label": "Filename prefix", "type": "string", "default": "batch"},
            {
                "name": "compression",
                "label": "Compression",
                "type": "select",
                "options": ["zstd", "snappy", "gzip", "none"],
                "default": "zstd",
            },
            {"name": "single_file", "label": "Single file", "type": "boolean", "default": False},
        ],
        default_node_template={"name": "sink.parquet", "kwargs": {}},
        supported_domains=["*"],
        tags=["parquet", "filesystem"],
    ),
    SinkKindDescriptor(
        kind="kafka",
        display_name="Kafka topic",
        description="Publish each row of every batch as a JSON message to a Kafka topic.",
        config_fields=[
            {"name": "topic", "label": "Topic", "type": "string", "required": True},
            {
                "name": "bootstrap_servers",
                "label": "Bootstrap servers",
                "type": "string",
            },
            {"name": "key_column", "label": "Key column", "type": "string"},
            {"name": "flush_every", "label": "Flush every (rows)", "type": "integer", "default": 1000},
        ],
        default_node_template={"name": "sink.kafka", "kwargs": {}},
        supported_domains=["bars.*", "events.*", "user.dataset"],
        tags=["kafka", "stream"],
    ),
    SinkKindDescriptor(
        kind="chroma",
        display_name="Chroma vector collection",
        description="Embed and write rows into a Chroma collection.",
        config_fields=[
            {"name": "collection", "label": "Collection name", "type": "string", "required": True},
            {"name": "text_column", "label": "Text column", "type": "string", "default": "text"},
        ],
        default_node_template={"name": "sink.chroma", "kwargs": {}},
        supported_domains=["text.*", "rag.*"],
        tags=["chroma", "vector"],
    ),
    SinkKindDescriptor(
        kind="profile",
        display_name="Profile cache",
        description="Compute a dataset profile and persist it to dataset_profiles.",
        config_fields=[
            {"name": "namespace", "label": "Namespace", "type": "string", "required": True},
            {"name": "table", "label": "Table", "type": "string", "required": True},
        ],
        default_node_template={"name": "sink.profile", "kwargs": {}},
        supported_domains=["*"],
        tags=["profiling"],
    ),
    SinkKindDescriptor(
        kind="dbt_build",
        display_name="dbt build target",
        description="Materialize batches as a dbt seed/source for downstream models.",
        config_fields=[
            {"name": "project_dir", "label": "dbt project directory", "type": "path"},
            {"name": "target", "label": "dbt target", "type": "string", "default": "dev"},
            {"name": "model", "label": "Model name", "type": "string"},
        ],
        default_node_template={"name": "sink.dbt_build", "kwargs": {}},
        supported_domains=["*"],
        tags=["dbt", "transform"],
    ),
    SinkKindDescriptor(
        kind="ml_feature_snapshot",
        display_name="ML feature snapshot (Iceberg + lineage)",
        description=(
            "Write preprocessed feature batches to an Iceberg table with "
            "ML lineage tags (pipeline_recipe_id, dataset_version_id, "
            "feature_snapshot_id) so downstream training runs can reload "
            "the exact features deterministically."
        ),
        config_fields=[
            {"name": "namespace", "label": "Namespace", "type": "string", "required": True},
            {"name": "table", "label": "Table", "type": "string", "required": True},
            {
                "name": "pipeline_recipe_id",
                "label": "Pipeline recipe id",
                "type": "string",
            },
            {
                "name": "dataset_version_id",
                "label": "Dataset version id",
                "type": "string",
            },
            {
                "name": "mode",
                "label": "Write mode",
                "type": "select",
                "options": ["append", "overwrite"],
                "default": "append",
            },
        ],
        default_node_template={"name": "sink.ml_feature_snapshot", "kwargs": {}},
        supported_domains=["ml.features.*", "user.dataset"],
        tags=["ml", "feature-store", "iceberg"],
    ),
)


def list_sink_kinds() -> list[SinkKindDescriptor]:
    """Return descriptor metadata for every registered sink kind.

    Used by the ``/sinks/kinds`` API and the SinkRegistry UI.
    """
    return list(_SINK_DESCRIPTORS)


def get_sink_descriptor(kind: str) -> SinkKindDescriptor | None:
    """Return the descriptor for ``kind`` or ``None`` if not registered."""
    target = (kind or "").strip().lower()
    for desc in _SINK_DESCRIPTORS:
        if desc.kind == target:
            return desc
    return None


__all__ = [
    "ChromaSink",
    "DbtBuildSink",
    "IcebergSink",
    "KafkaSink",
    "MlFeatureSnapshotSink",
    "ParquetSink",
    "ProfileSink",
    "SinkKindDescriptor",
    "get_sink_descriptor",
    "list_sink_kinds",
]
