"""OpenMetadata-style models for pipeline metadata aspects."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import ClassVar

from pydantic import Field, ValidationInfo, field_validator

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase, _urn_validator

logger = logging.getLogger(__name__)


class PipelineTask(AQPOpenMetadataBase):
    """Single task node inside a pipeline DAG definition."""

    name: str = Field(..., description="Task name, unique within the pipeline.")
    task_type: str = Field(
        ...,
        description="One of the canonical lineage transform kinds.",
    )
    upstream_tasks: list[str] = Field(
        default_factory=list,
        description="Names of tasks that must complete before this task starts.",
    )
    description: str | None = Field(
        default=None,
        description="Operator-readable description of what this task does.",
    )
    start_date: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when this task started.",
    )
    end_date: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when this task finished.",
    )

    @field_validator("task_type", mode="after")
    @classmethod
    def _validate_task_type(cls, value: str, info: ValidationInfo) -> str:
        """Validate task type against canonical lineage transform kinds."""
        from aqp.persistence.models_lineage import LINEAGE_TRANSFORM_KINDS

        candidate = str(value).strip()
        if candidate not in LINEAGE_TRANSFORM_KINDS:
            field_name = info.field_name or "task_type"
            raise ValueError(
                f"Invalid task type in field '{field_name}': {value!r}. "
                f"Expected one of {LINEAGE_TRANSFORM_KINDS}."
            )
        return candidate


class Pipeline(AQPOpenMetadataBase):
    """OpenMetadata-style representation of a pipeline entity."""

    entity_type: ClassVar[str] = "pipeline"
    aspect_name: ClassVar[str] = "pipelineMetadata"

    urn: str = Field(
        ...,
        description=(
            "AQP URN of the pipeline, eg. "
            "urn:aqp:pipeline:prod:nightly_alpha_research."
        ),
    )
    name: str = Field(..., description="Human-friendly pipeline name.")
    pipeline_location: str = Field(
        ...,
        description=(
            "Where the pipeline lives - eg. file path, Dagster job ID, "
            "Argo Workflow template name."
        ),
    )
    tasks: list[PipelineTask] = Field(
        default_factory=list,
        description="DAG of pipeline tasks.",
    )
    start_date: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when the pipeline run started.",
    )
    end_date: datetime | None = Field(
        default=None,
        description="Optional UTC timestamp when the pipeline run ended.",
    )

    _validate_urn = _urn_validator("urn")


__all__ = ["Pipeline", "PipelineTask"]
