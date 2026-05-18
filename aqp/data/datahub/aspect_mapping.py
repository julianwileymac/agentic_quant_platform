"""Mapping between AQP EntityAspect names and DataHub aspect classes.

DataHub uses Pegasus-v1 dataclasses (``MLModelPropertiesClass``,
``DatasetPropertiesClass``, etc.) keyed by URN entity-type. AQP's
canonical aspect store keeps a smaller, opinionated vocabulary
(``mlModelMetadata``, ``datasetProperties``, ``businessMetadata`` ...).
The mapping is intentionally lossy on the DataHub side — the AQP
aspect store remains authoritative; DataHub gets the closest
representation we can build without losing the original JSON
payload.

The lazy import + ``try/except ImportError`` pattern matches
:mod:`aqp.data.datahub.emitter` — every public function returns
``None`` (or ``{"emitted": False, "error": ...}`` at the caller) when
the optional ``acryl-datahub`` extra is missing.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from aqp.config import settings
from aqp.metadata.urn import parse_urn

logger = logging.getLogger(__name__)


ASPECT_TO_DATAHUB_CLASS: dict[str, str] = {
    "mlModelMetadata": "MLModelPropertiesClass",
    "datasetProperties": "DatasetPropertiesClass",
    "businessMetadata": "GlobalTagsClass",
    "dataContract": "SchemaMetadataClass",
    "entityProperties": "InstitutionalMemoryClass",
    "lineageEdge": "UpstreamLineageClass",
    "documentMetadata": "InstitutionalMemoryClass",
    "mlTestResult": "MLModelTrainingDataClass",
    "pipelineMetadata": "DataJobInfoClass",
    "icebergNamespacePolicy": "GlobalTagsClass",
}


def aqp_urn_to_datahub_entity_urn(aqp_urn: str, *, platform: str | None = None) -> str:
    """Convert an AQP URN into a DataHub-style entity URN.

    Adapts the entity-type prefix per :data:`ASPECT_TO_DATAHUB_CLASS`:

    - ``urn:aqp:dataset:prod:foo.bar`` →
      ``urn:li:dataset:(urn:li:dataPlatform:aqp,foo.bar,PROD)``
    - ``urn:aqp:mlmodel:prod:lstm_v1`` →
      ``urn:li:mlModel:(urn:li:dataPlatform:aqp,lstm_v1,PROD)``
    - ``urn:aqp:pipeline:prod:nightly_alpha`` →
      ``urn:li:dataJob:(urn:li:dataFlow:(urn:li:dataPlatform:aqp,nightly_alpha,PROD),task)``
    - ``urn:aqp:document:prod:sec_10k_001`` →
      ``urn:li:dataset:(urn:li:dataPlatform:aqp,document/sec_10k_001,PROD)``

    Reserved chars in the id (parens, commas, U+241F) are URL-encoded.
    Unknown entity types fall back to ``urn:li:{type}:{platform}.{id}``.
    """
    parsed = parse_urn(aqp_urn)
    platform_clean = (
        str(platform or settings.datahub_platform or "aqp").strip() or "aqp"
    )
    env_label = parsed.env.upper()
    encoded_id = quote(parsed.id, safe="._:-")

    entity_type = parsed.entity_type
    if entity_type == "dataset":
        return (
            f"urn:li:dataset:(urn:li:dataPlatform:{platform_clean},"
            f"{encoded_id},{env_label})"
        )
    if entity_type == "mlmodel":
        return (
            f"urn:li:mlModel:(urn:li:dataPlatform:{platform_clean},"
            f"{encoded_id},{env_label})"
        )
    if entity_type == "pipeline":
        return (
            f"urn:li:dataJob:(urn:li:dataFlow:(urn:li:dataPlatform:"
            f"{platform_clean},{encoded_id},{env_label}),task)"
        )
    if entity_type == "document":
        return (
            f"urn:li:dataset:(urn:li:dataPlatform:{platform_clean},"
            f"document/{encoded_id},{env_label})"
        )
    return f"urn:li:{entity_type}:{platform_clean}.{encoded_id}"


def build_datahub_aspect(aspect_name: str, payload: dict[str, Any]) -> Any | None:
    """Construct the DataHub aspect dataclass for a given AQP aspect.

    Returns ``None`` when the optional ``acryl-datahub`` extra is not
    installed (so callers can short-circuit with a clean
    ``{"emitted": False, "error": "datahub SDK unavailable"}``).

    Each AQP aspect has a small adapter function that maps its payload
    into the closest DataHub equivalent. Unknown aspect names fall back
    to ``GlobalTagsClass`` with no tags (a DataHub no-op).
    """
    schema_classes = _load_schema_classes()
    if schema_classes is None:
        return None

    adapter = _ADAPTERS.get(aspect_name, _build_global_tags_fallback)
    try:
        return adapter(schema_classes, payload)
    except Exception:  # noqa: BLE001
        logger.warning(
            "build_datahub_aspect adapter failed for %s", aspect_name, exc_info=True
        )
        return None


def _load_schema_classes() -> Any | None:
    try:
        from datahub.metadata import schema_classes
    except ImportError:
        return None
    except Exception:  # noqa: BLE001
        return None
    return schema_classes


def _stringify_custom_properties(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in value.items():
        if v is None:
            out[str(k)] = ""
        elif isinstance(v, (str, int, float, bool)):
            out[str(k)] = str(v)
        else:
            try:
                import json

                out[str(k)] = json.dumps(v, sort_keys=True, default=str)
            except Exception:  # noqa: BLE001
                out[str(k)] = str(v)
    return out


def _build_ml_model_properties(
    schema_classes: Any, payload: dict[str, Any]
) -> Any | None:
    cls = getattr(schema_classes, "MLModelPropertiesClass", None)
    if cls is None:
        return None
    custom_properties = _stringify_custom_properties(
        {
            "algorithm": payload.get("algorithm"),
            "target": payload.get("target"),
            "status": payload.get("status"),
            "model_version": payload.get("model_version"),
            "mlflow_run_id": payload.get("mlflow_run_id"),
            "feature_count": len(payload.get("ml_features") or []),
            "hyperparameter_count": len(payload.get("ml_hyper_parameters") or []),
        }
    )
    return cls(
        description=str(payload.get("name") or payload.get("description") or ""),
        customProperties=custom_properties,
        type=str(payload.get("algorithm") or "unknown"),
    )


def _build_dataset_properties(
    schema_classes: Any, payload: dict[str, Any]
) -> Any | None:
    cls = getattr(schema_classes, "DatasetPropertiesClass", None)
    if cls is None:
        return None
    custom_properties = _stringify_custom_properties(
        {
            "medallion_layer": payload.get("medallion_layer"),
            "iceberg_identifier": payload.get("iceberg_identifier"),
            **(payload.get("business_metadata") or {}),
        }
    )
    return cls(
        description=str(payload.get("description") or ""),
        customProperties=custom_properties,
        name=str(payload.get("name") or payload.get("iceberg_identifier") or ""),
    )


def _build_global_tags(schema_classes: Any, payload: dict[str, Any]) -> Any | None:
    tags_cls = getattr(schema_classes, "GlobalTagsClass", None)
    assoc_cls = getattr(schema_classes, "TagAssociationClass", None)
    if tags_cls is None or assoc_cls is None:
        return None
    candidate_tags: list[str] = []
    for key in ("data_owner", "domain", "sla_class"):
        v = payload.get(key)
        if v:
            candidate_tags.append(f"{key}:{v}")
    candidate_tags.extend(payload.get("tags") or [])
    return tags_cls(
        tags=[
            assoc_cls(tag=f"urn:li:tag:{tag}")
            for tag in dict.fromkeys(candidate_tags)
            if tag
        ]
    )


def _build_global_tags_fallback(
    schema_classes: Any, payload: dict[str, Any]
) -> Any | None:
    """Fallback adapter for unknown aspect names — emits zero tags."""
    tags_cls = getattr(schema_classes, "GlobalTagsClass", None)
    if tags_cls is None:
        return None
    return tags_cls(tags=[])


def _build_schema_metadata(
    schema_classes: Any, payload: dict[str, Any]
) -> Any | None:
    cls = getattr(schema_classes, "SchemaMetadataClass", None)
    other_cls = getattr(schema_classes, "OtherSchemaClass", None)
    field_cls = getattr(schema_classes, "SchemaFieldClass", None)
    string_type_cls = getattr(schema_classes, "StringTypeClass", None)
    field_type_cls = getattr(schema_classes, "SchemaFieldDataTypeClass", None)
    if (
        cls is None
        or field_cls is None
        or string_type_cls is None
        or field_type_cls is None
        or other_cls is None
    ):
        return None
    columns = payload.get("columns") or []
    fields = [
        field_cls(
            fieldPath=str(col.get("name") or ""),
            type=field_type_cls(type=string_type_cls()),
            nativeDataType=str(col.get("type") or "string"),
            nullable=bool(col.get("required") is not True),
        )
        for col in columns
        if isinstance(col, dict) and col.get("name")
    ]
    return cls(
        schemaName="aqp.dataContract",
        platform="urn:li:dataPlatform:aqp",
        version=0,
        hash="",
        platformSchema=other_cls(rawSchema=str(payload.get("description") or "")),
        fields=fields,
    )


def _build_institutional_memory(
    schema_classes: Any, payload: dict[str, Any]
) -> Any | None:
    cls = getattr(schema_classes, "InstitutionalMemoryClass", None)
    elem_cls = getattr(schema_classes, "InstitutionalMemoryMetadataClass", None)
    audit_cls = getattr(schema_classes, "AuditStampClass", None)
    if cls is None or elem_cls is None or audit_cls is None:
        return None
    url = str(payload.get("source_url") or "")
    description = str(
        payload.get("content_text")
        or payload.get("description")
        or "AQP document aspect"
    )
    if not url:
        return cls(elements=[])
    actor = "urn:li:corpuser:aqp"
    return cls(
        elements=[
            elem_cls(
                url=url,
                description=description[:512],
                createStamp=audit_cls(time=0, actor=actor),
            )
        ]
    )


def _build_upstream_lineage(
    schema_classes: Any, payload: dict[str, Any]
) -> Any | None:
    cls = getattr(schema_classes, "UpstreamLineageClass", None)
    upstream_cls = getattr(schema_classes, "UpstreamClass", None)
    audit_cls = getattr(schema_classes, "AuditStampClass", None)
    lineage_type_cls = getattr(schema_classes, "DatasetLineageTypeClass", None)
    if cls is None or upstream_cls is None or audit_cls is None or lineage_type_cls is None:
        return None
    from_entity = str(payload.get("from_entity") or "")
    if not from_entity:
        return cls(upstreams=[])
    upstream_datahub_urn = (
        aqp_urn_to_datahub_entity_urn(from_entity)
        if from_entity.startswith("urn:aqp:")
        else from_entity
    )
    actor = "urn:li:corpuser:aqp"
    return cls(
        upstreams=[
            upstream_cls(
                dataset=upstream_datahub_urn,
                type=getattr(lineage_type_cls, "TRANSFORMED", "TRANSFORMED"),
                auditStamp=audit_cls(time=0, actor=actor),
            )
        ]
    )


def _build_ml_model_training_data(
    schema_classes: Any, payload: dict[str, Any]
) -> Any | None:
    """Fallback to MLModelPropertiesClass with metric custom properties."""
    model_cls = getattr(schema_classes, "MLModelPropertiesClass", None)
    if model_cls is None:
        return None
    custom_properties = _stringify_custom_properties(
        {
            "sharpe_ratio": payload.get("sharpe_ratio"),
            "max_drawdown": payload.get("max_drawdown"),
            "agreement_rate": payload.get("agreement_rate"),
            "accuracy": payload.get("accuracy"),
            "test_id": payload.get("test_id"),
            "started_at": payload.get("started_at"),
            "completed_at": payload.get("completed_at"),
            **_stringify_custom_properties(payload.get("extra_metrics") or {}),
        }
    )
    return model_cls(
        description="AQP mlTestResult",
        customProperties=custom_properties,
        type="test_result",
    )


def _build_data_job_info(
    schema_classes: Any, payload: dict[str, Any]
) -> Any | None:
    cls = getattr(schema_classes, "DataJobInfoClass", None)
    if cls is None:
        return None
    custom_properties = _stringify_custom_properties(
        {
            "pipeline_location": payload.get("pipeline_location"),
            "task_count": len(payload.get("tasks") or []),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
        }
    )
    return cls(
        name=str(payload.get("name") or "aqp_pipeline"),
        type="COMMAND",
        customProperties=custom_properties,
    )


_ADAPTERS = {
    "mlModelMetadata": _build_ml_model_properties,
    "datasetProperties": _build_dataset_properties,
    "businessMetadata": _build_global_tags,
    "dataContract": _build_schema_metadata,
    "entityProperties": _build_institutional_memory,
    "lineageEdge": _build_upstream_lineage,
    "documentMetadata": _build_institutional_memory,
    "mlTestResult": _build_ml_model_training_data,
    "pipelineMetadata": _build_data_job_info,
    "icebergNamespacePolicy": _build_global_tags,
}


__all__ = [
    "ASPECT_TO_DATAHUB_CLASS",
    "aqp_urn_to_datahub_entity_urn",
    "build_datahub_aspect",
]
