# PreprocessingSpec

A `PreprocessingSpec` is a tiny dataclass that travels with every trained
model artifact. It remembers which processors were fit and in what order
so inference code can replay the exact preprocessing chain on new data
without ever reaching back into the training-time configuration.

## Why

Qlib's `DataHandlerLP` applies an ordered chain of `Processor` steps
(rank-norm, z-score, min-max, outlier clipping, etc.) during training.
At inference time the *same* chain must be re-applied — otherwise the
model is scored on data with a different distribution than it was trained
on, which silently degrades live performance.

Until now this was only tracked implicitly (the handler config was
expected to be re-instantiated exactly). `PreprocessingSpec` makes it
explicit: the spec is serialised into the model pickle and reloaded when
the model is served, backtested, or paper-traded.

## Shape

```python
@dataclass
class PreprocessingSpec:
    processors_pickle: bytes                # fit state for exact replay
    processor_specs: list[dict]             # {class, module_path, kwargs}
    feature_columns: list[str]
    label_column: str | None
    handler_cfg: dict | None
    metadata: dict[str, Any]
```

## Training-side usage

```python
from aqp.ml.processors import PreprocessingSpec
from aqp.ml.handler import DataHandlerLP

handler = DataHandlerLP(
    instruments=[...],
    learn_processors=[...],
    infer_processors=[...],
)
handler.setup_data()

spec = PreprocessingSpec.from_processors(
    processors=handler.infer_processors,
    feature_columns=[...],
    label_column="label_5d",
    handler_cfg={"class": "DataHandlerLP", "module_path": "aqp.ml.handler", "kwargs": {...}},
    metadata={"dataset_hash": "abc123", "fit_window": "2020-01-01..2023-12-31"},
)

model.fit(dataset).with_preprocessing(spec)
model.to_pickle("models/alpha_v1.pkl")
```

## Inference-side usage

```python
from aqp.ml.base import Model

model = Model.from_pickle("models/alpha_v1.pkl")
spec = model.preprocessing_spec
if spec is not None:
    df = spec.apply(new_bars)       # replay the chain, no re-fit
preds = model.predict(df)
```

## Serving-side usage

All three serving backends (`MLflowServe`, `RayServe`, `TorchServe`) know
about `preprocessing_spec`. The TorchServe handler in
[`aqp/mlops/serving/torchserve.py`](../../aqp/mlops/serving/torchserve.py)
calls `spec.apply(df)` before `model.predict(df)` when the attribute is
present.
