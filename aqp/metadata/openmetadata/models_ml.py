"""OpenMetadata-style models for ML entities and aspects."""
from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from typing import Any, ClassVar, Literal, get_args

from pydantic import Field, ValidationInfo, field_validator

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase, _urn_validator

logger = logging.getLogger(__name__)


class FeatureSource(AQPOpenMetadataBase):
    """Describes an upstream source column used to derive an ML feature."""

    source_urn: str = Field(
        ...,
        description=(
            "AQP URN of the originating dataset/column the feature was derived from."
        ),
    )
    source_data_type: str = Field(
        ...,
        description="PyArrow / SQL data type of the upstream column, eg. 'float64', 'string'.",
    )
    source_tags: list[str] = Field(
        default_factory=list,
        description="Free-form tags propagated from the source column.",
    )

    _validate_source_urn = _urn_validator("source_urn")


class MlFeature(AQPOpenMetadataBase):
    """Feature metadata stored alongside ML model metadata aspects."""

    name: str = Field(..., description="Feature name as referenced by the model.")
    data_type: Literal["numerical", "categorical", "timestamp", "array", "struct"] = (
        Field(..., description="High-level Arrow type family.")
    )
    feature_sources: list[FeatureSource] = Field(
        default_factory=list,
        description=(
            "Upstream column sources. Each source must carry a source_urn "
            "referencing a registered dataset URN."
        ),
    )
    feature_algorithm: str | None = Field(
        default=None,
        description=(
            "Transformation logic that produced the feature, eg. "
            "'rolling z-score(20)', 'log-return(close)'."
        ),
    )


class MlHyperParameter(AQPOpenMetadataBase):
    """Single hyperparameter/value pair captured as OpenMetadata payload."""

    name: str = Field(
        ...,
        description="Hyperparameter name as it appears in the model factory kwargs.",
    )
    value: str = Field(
        ...,
        description="Hyperparameter value serialised as a string for type neutrality.",
    )
    value_type: str = Field(
        ...,
        description="Cast hint, eg. 'int', 'float', 'str', 'bool', 'json'.",
    )
    description: str = Field(
        ...,
        description="Operator-readable description of what this hyperparameter does.",
    )


@lru_cache(maxsize=1)
def _resolve_algorithm_choices() -> tuple[str, ...]:
    """Resolve valid model algorithm choices from registry with fallback defaults."""

    baseline: tuple[str, ...] = (
        "xgb_regressor",
        "lstm_classifier",
        "linear_regression",
        "logistic_regression",
        "random_forest",
        "naive_bayes",
        "lightgbm_classifier",
        "lightgbm_regressor",
        "transformer",
        "prophet",
        "auto_arima",
        "tcn",
        "tabnet",
        "gru",
        "lstm",
        "mlp",
        "ridge",
        "ensemble",
        "custom",
    )
    choices: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        cleaned = str(value).strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            choices.append(cleaned)

    try:
        from aqp.core import registry as core_registry

        try:
            import aqp.ml.models  # noqa: F401
        except Exception as exc:  # pragma: no cover - optional deps
            logger.debug("Unable to import aqp.ml.models for registry warmup: %s", exc)

        list_by_kind = getattr(core_registry, "list_by_kind", None)
        if callable(list_by_kind):
            model_registry = list_by_kind("model")
            if isinstance(model_registry, dict):
                for name in sorted(model_registry):
                    _add(name)
        kind_index = getattr(core_registry, "_kind_index", None)
        if isinstance(kind_index, dict):
            model_registry = kind_index.get("model", {})
            if isinstance(model_registry, dict):
                for name in sorted(model_registry):
                    _add(name)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Unable to inspect AQP model registry: %s", exc)

    try:
        from aqp.ml.predictors.spec import ModelKind

        for model_kind in get_args(ModelKind):
            _add(str(model_kind))
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Unable to read PredictorSpec model kinds: %s", exc)

    for default_choice in baseline:
        _add(default_choice)
    if "custom" in seen and choices[-1] != "custom":
        choices = [choice for choice in choices if choice != "custom"] + ["custom"]
    return tuple(choices)


class MlModel(AQPOpenMetadataBase):
    """OpenMetadata-style representation of an AQP ML model entity."""

    entity_type: ClassVar[str] = "mlmodel"
    aspect_name: ClassVar[str] = "mlModelMetadata"

    urn: str = Field(
        ...,
        description="AQP URN of the ML model, eg. urn:aqp:mlmodel:prod:lstm_classifier_v3.",
    )
    name: str = Field(..., description="Human-friendly model name.")
    algorithm: str = Field(
        ...,
        description=(
            "Algorithm used by the model. Must match a registered AQP model "
            "factory or a known PredictorSpec.model_kind value."
        ),
    )
    ml_features: list[MlFeature] = Field(
        default_factory=list,
        description="Features used to train the model.",
    )
    ml_hyper_parameters: list[MlHyperParameter] = Field(
        default_factory=list,
        description="Hyperparameters used during training.",
    )
    target: str = Field(
        ...,
        description=(
            "Predicted variable, eg. 'forward_return_1d', "
            "'volatility_forecast', 'direction_label'."
        ),
    )
    status: Literal["Development", "Staging", "Production", "Deprecated"] = Field(
        ...,
        description="Model lifecycle status. Paper-trading sessions only accept Staging or Production.",
    )
    model_version: str | None = Field(
        default=None,
        description="Optional human-readable model version, eg. 'v3.2.1'.",
    )
    mlflow_run_id: str | None = Field(
        default=None,
        description="Optional linked MLflow run ID for cross-reference.",
    )

    _validate_urn = _urn_validator("urn")

    @field_validator("algorithm", mode="after")
    @classmethod
    def _validate_algorithm(cls, value: str, info: ValidationInfo) -> str:
        """Ensure algorithm names resolve against registered/fallback choices."""
        candidate = str(value).strip().lower()
        choices = _resolve_algorithm_choices()
        if candidate not in choices:
            field_name = info.field_name or "algorithm"
            raise ValueError(
                f"Invalid algorithm in field '{field_name}': {value!r}. "
                f"Expected one of {choices}."
            )
        return candidate


class MlTestResult(AQPOpenMetadataBase):
    """Captures benchmark and prediction quality metrics for a model test run."""

    entity_type: ClassVar[str] = "mlmodel"
    aspect_name: ClassVar[str] = "mlTestResult"

    model_urn: str = Field(
        ...,
        description="URN of the MlModel this test was run against.",
    )
    test_id: str = Field(
        ...,
        description="Unique identifier for this test run, eg. UUID.",
    )
    started_at: datetime = Field(
        ...,
        description="UTC timestamp when the test run began.",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the test run completed.",
    )
    sharpe_ratio: float | None = Field(
        default=None,
        description="Sharpe ratio of the test-period strategy returns.",
    )
    max_drawdown: float | None = Field(
        default=None,
        description="Maximum drawdown of the test-period strategy.",
    )
    agreement_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Agreement rate between predictions and ground truth (0..1).",
    )
    accuracy: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Classification accuracy where applicable.",
    )
    extra_metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional named metrics that don't have a dedicated field.",
    )

    _validate_model_urn = _urn_validator("model_urn")


__all__ = [
    "FeatureSource",
    "MlFeature",
    "MlHyperParameter",
    "MlModel",
    "MlTestResult",
]
