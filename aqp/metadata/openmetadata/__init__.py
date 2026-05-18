"""OpenMetadata Pydantic V2 layer for AQP metadata payloads."""
from __future__ import annotations

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase
from aqp.metadata.openmetadata.models_glossary import Document, GlossaryTerm
from aqp.metadata.openmetadata.models_lineage import EntityLineage, LineageEdge
from aqp.metadata.openmetadata.models_ml import (
    FeatureSource,
    MlFeature,
    MlHyperParameter,
    MlModel,
    MlTestResult,
)
from aqp.metadata.openmetadata.models_namespace import NamespacePrefixOverride
from aqp.metadata.openmetadata.models_pipeline import Pipeline, PipelineTask
from aqp.metadata.openmetadata.models_table import (
    DatasetTable,
    IcebergNamespacePolicy,
    TableColumn,
    TableConstraint,
)

__all__ = [
    "AQPOpenMetadataBase",
    "MlFeature",
    "FeatureSource",
    "MlHyperParameter",
    "MlModel",
    "MlTestResult",
    "IcebergNamespacePolicy",
    "NamespacePrefixOverride",
    "Pipeline",
    "PipelineTask",
    "DatasetTable",
    "TableColumn",
    "TableConstraint",
    "LineageEdge",
    "EntityLineage",
    "GlossaryTerm",
    "Document",
]
