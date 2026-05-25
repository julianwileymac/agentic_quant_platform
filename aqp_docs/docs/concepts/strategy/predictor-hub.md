---
title: 'PredictorHub'
summary: 'The report calls out two empirical findings from the literature:'
owner: ml-team
last_reviewed: 2026-05-25
audience: both
---

# PredictorHub

> Status: **Phase 5 shipped** (Alembic 0044). Hub:
> [`aqp/ml/predictors/`](../aqp/ml/predictors/).

## Why unify

The report calls out two empirical findings from the literature:

* **XGBoost regression** -- significantly superior accuracy at pure
  numerical return prediction (low-noise, structured features)
* **LSTM classification** -- demonstrably better at directional
  classification over medium-term 7-30 day horizons (sequence-aware,
  handles regime shifts)

The platform already had both models available under
[`aqp/ml/models/`](../aqp/ml/models/), but they were registered with
different config keys, trained via different code paths, and
serialised inconsistently. Phase 5 consolidates them under a single
:class:`PredictorSpec` shape that the hub uses to pick the right
factory.

## PredictorSpec

The spec is hash-locked Pydantic:

```python
from aqp.ml.predictors import PredictorSpec

# XGBoost regression — predict next-day return
spec_xgb = PredictorSpec(
    name="xgb_returns_1d",
    model_kind="xgboost",
    label_kind="regression",
    target_horizon="1d",
    feature_columns=["mom_5", "mom_20", "rsi_14", "vol_20"],
    target_column="ret_1d",
    hyperparams={"max_depth": 6, "learning_rate": 0.05, "n_estimators": 500},
)

# LSTM classification — predict 20-day direction (binary)
spec_lstm = PredictorSpec(
    name="lstm_direction_20d",
    model_kind="lstm",
    label_kind="classification",
    target_horizon="20d",
    feature_columns=["close", "volume", "rsi_14", "macd"],
    target_column="dir_20d",
    sequence_length=60,
    hyperparams={"hidden_size": 64, "num_layers": 2, "dropout": 0.2},
    classes=["down", "up"],
)
```

Re-snapshotting the spec into the persistence layer:

```python
from aqp.ml.predictors import persist_predictor_spec

row_id, created = persist_predictor_spec(spec_xgb)
print(row_id, created)  # created=True the first time, False if hash unchanged
```

## PredictorHub

```python
from aqp.ml.predictors import PredictorHub

hub = PredictorHub()
model = hub.build(spec_xgb)
model.fit(X_train, y_train)
preds = model.predict(X_test)
```

The hub picks the right factory from the
``(model_kind, label_kind)`` registry. Adding a new model:

```python
from aqp.ml.predictors import register_predictor

@register_predictor(model_kind="transformer", label_kind="classification")
def my_transformer_factory(spec):
    ...
    return TransformerClassifier(**spec.hyperparams)
```

## Reference factories

The hub ships four reference factories matching the report's
recommendations:

| ``model_kind`` | ``label_kind`` | Underlying class |
| --- | --- | --- |
| ``xgboost`` | ``regression`` | :class:`XGBModel` from :mod:`aqp.ml.models.tree` |
| ``xgboost`` | ``classification`` | :class:`XGBModel` (with binary or multi-class objective) |
| ``lstm`` | ``classification`` | :class:`LSTMModel` from :mod:`aqp.ml.models.torch.lstm` |
| ``lstm`` | ``regression`` | :class:`LSTMModel` (regression head) |

## Hash-locked versioning

The Phase 5 ``predictor_spec_versions`` table mirrors the spec-version
pattern used by AgentSpec / BotSpec / RLExperimentSpec /
AnalysisSpec. Re-running ``persist_predictor_spec`` with an unchanged
spec returns ``created=False``; a single byte change to the spec body
(new feature, new hyperparam) produces a fresh row. This means every
"how was this model trained?" question has a precise answer pinned
by the SHA-256 hash.

## Wiring into agents

Phase 5 exposes the hub through the existing
[`/ml/test`](../aqp/api/routes/ml.py) endpoints (REST) and three
DataMCP tools (agent-facing):

* ``data.ml.predictors.list`` -- list registered specs
* ``data.ml.predictors.train`` -- snapshot a spec + train
* ``data.ml.predictors.deploy_pair`` -- A/B-test two trained models

Agents query the catalogue first, snapshot a spec, train, and
deploy without an ORM import.
