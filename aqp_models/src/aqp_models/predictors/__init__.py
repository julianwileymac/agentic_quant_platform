"""Unified ML predictor hub.

Phase 5 (Alembic 0044) consolidates the platform's regression +
classification model factories under a single :class:`PredictorSpec`
shape. The two reference cases the report calls out:

* **XGBoost regression** for numerical return prediction (best for
  pure regression tasks)
* **LSTM classification** for directional movement over medium
  horizons (best for 7-30 day directional classification)

Both fit the same :class:`PredictorSpec` template -- the underlying
model factory + hyperparams differ but the dispatch is uniform.

The spec is hash-locked (mirrors ``AgentSpec`` / ``BotSpec`` /
``RLExperimentSpec`` / ``AnalysisSpec``); re-snapshotting a changed
spec creates a new ``predictor_spec_versions`` row, never an in-place
mutation (AGENTS rules 13 / 15 / 17 / 24).
"""
from __future__ import annotations

from aqp_models.predictors.spec import (
    PredictorSpec,
    persist_predictor_spec,
)
from aqp_models.predictors.hub import (
    PredictorHub,
    list_predictors,
    register_predictor,
)

__all__ = [
    "PredictorHub",
    "PredictorSpec",
    "list_predictors",
    "persist_predictor_spec",
    "register_predictor",
]
