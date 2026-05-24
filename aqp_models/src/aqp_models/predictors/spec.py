"""PredictorSpec -- hash-locked snapshot of a predictive model recipe.

Mirrors :class:`aqp.agents.spec.AgentSpec` / :class:`aqp.bots.spec.BotSpec` /
:class:`aqp.rl.spec.RLExperimentSpec` / :class:`aqp.analysis.spec.AnalysisSpec`:
a Pydantic body + a SHA-256 hash + persistence via a ``*_spec_versions``
row. Changing the spec body means a new version row, never an in-place
mutation.

The spec drives both:

* **Training** -- the :class:`PredictorHub` reads the spec to build the
  matching model factory and runs a single training pass.
* **Inference** -- the bot / strategy layer reads the spec to know
  which features to materialise + which model to call.

The shape is intentionally tight: ``model_kind`` discriminates the
underlying library (XGBoost, LSTM, transformer, linear, TCN) and
``label_kind`` (regression / classification / ranking) selects the
loss function.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


ModelKind = Literal["xgboost", "lstm", "transformer", "linear", "tcn", "lightgbm", "random_forest"]
LabelKind = Literal["regression", "classification", "ranking"]
TargetHorizon = Literal["1d", "5d", "10d", "20d", "30d", "60d", "90d", "event", "adhoc"]


class PredictorSpec(BaseModel):
    """Hash-locked predictor spec.

    Used by both training (the hub fits the model) and inference (the
    bot / strategy reads the feature list + model id to call).

    Example -- the two reference cases the report calls out:

    .. code-block:: python

        # XGBoost regression: predict next-day return
        spec_xgb = PredictorSpec(
            name="xgb_returns_1d",
            model_kind="xgboost",
            label_kind="regression",
            target_horizon="1d",
            feature_columns=["mom_5", "mom_20", "rsi_14", "vol_20"],
            target_column="ret_1d",
            hyperparams={"max_depth": 6, "learning_rate": 0.05, "n_estimators": 500},
        )

        # LSTM classification: predict 20-day direction
        spec_lstm = PredictorSpec(
            name="lstm_direction_20d",
            model_kind="lstm",
            label_kind="classification",
            target_horizon="20d",
            feature_columns=["close", "volume", "rsi_14", "macd"],
            target_column="dir_20d",
            sequence_length=60,
            hyperparams={"hidden_size": 64, "num_layers": 2, "dropout": 0.2},
        )
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    model_kind: ModelKind
    label_kind: LabelKind
    target_horizon: TargetHorizon
    feature_columns: list[str]
    target_column: str
    sequence_length: int | None = None
    # LSTM / TCN / Transformer require a window of past observations
    hyperparams: dict[str, Any] = Field(default_factory=dict)
    preprocessing: dict[str, Any] = Field(default_factory=dict)
    # Optional pre-fit transforms (standardize / zscore / detrend / log_returns)
    validation_strategy: str = "walk_forward"
    # walk_forward | k_fold | time_series_split | hold_out
    validation_horizon: str | None = None
    cv_folds: int | None = None
    classes: list[str] | None = None
    # Classification only: explicit class labels (otherwise auto)
    universe: list[str] | None = None
    # Optional universe filter (vt_symbol list)
    workspace_id: str | None = None
    project_id: str | None = None

    # ------------------------------------------------------------------
    # Hash
    # ------------------------------------------------------------------

    def canonical_body(self) -> dict[str, Any]:
        """JSON-canonical body used for the hash + persistence."""
        return self.model_dump(exclude={"workspace_id", "project_id"}, mode="json")

    def spec_hash(self) -> str:
        """SHA-256 of the canonical body."""
        canonical = json.dumps(self.canonical_body(), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_regression(self) -> bool:
        return self.label_kind == "regression"

    @property
    def is_classification(self) -> bool:
        return self.label_kind == "classification"

    def is_xgb(self) -> bool:
        return self.model_kind == "xgboost"

    def is_lstm(self) -> bool:
        return self.model_kind == "lstm"


def persist_predictor_spec(spec: PredictorSpec) -> tuple[str, bool]:
    """Persist ``spec`` into ``predictor_spec_versions`` if its hash is new.

    Returns ``(version_row_id, created)``. ``created=False`` means the
    spec already had a snapshot row with the same hash; callers can
    safely re-snapshot every training run.
    """
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_predictors import PredictorSpecVersionRow
    except Exception as exc:  # noqa: BLE001
        logger.warning("predictor spec persistence unavailable: %s", exc)
        return ("", False)
    hash_val = spec.spec_hash()
    with get_session() as session:
        existing = session.execute(
            select(PredictorSpecVersionRow).where(
                PredictorSpecVersionRow.predictor_name == spec.name,
                PredictorSpecVersionRow.spec_hash == hash_val,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return (existing.id, False)
        row = PredictorSpecVersionRow(
            predictor_name=spec.name,
            spec_hash=hash_val,
            spec_body=spec.canonical_body(),
            model_kind=spec.model_kind,
            target_horizon=spec.target_horizon,
            label_kind=spec.label_kind,
            feature_columns=list(spec.feature_columns),
            hyperparams_json=dict(spec.hyperparams),
            description=spec.description,
            workspace_id=spec.workspace_id,
            project_id=spec.project_id,
            created_at=datetime.utcnow(),
        )
        session.add(row)
        session.flush()
        return (row.id, True)


__all__ = [
    "LabelKind",
    "ModelKind",
    "PredictorSpec",
    "TargetHorizon",
    "persist_predictor_spec",
]
