# ML preprocessing as data-pipeline nodes

> Bridges [`aqp.ml.processors`](../aqp/ml/processors.py) into the data
> engine ([`aqp/data/engine`](../aqp/data/engine/)) so an
> ``aqp.data.engine.PipelineManifest`` can chain
> ``source -> ml_preprocessing -> sink`` like any other transform.

## Why

Before this expansion, the only way to apply an ML preprocessing
recipe was to load a `Dataset` and call `Processor.fit_process` —
which only works for offline `Experiment` runs. Promoting processors
to first-class data-engine nodes lets you:

- Materialise preprocessed features into Iceberg via
  ``sink.ml_feature_snapshot`` and reload them deterministically in
  later training runs.
- Reuse the same recipe in batch ingestion AND online inference.
- Drop a saved ``PipelineRecipe`` row directly onto the manifest
  builder canvas via ``POST /ml/pipelines/{id}/as-node``.

## Two layers

### Umbrella node — `transform.ml_preprocessing`

Accepts either a saved ``recipe_id`` or an inline ``processors`` list.
Re-uses [`apply_processor_specs`](../aqp/ml/pipeline_recipes.py) so a
manifest run applies the same transformation as the offline ML
training loop.

```yaml
- name: transform.ml_preprocessing
  kwargs:
    recipe_id: 1c5b...    # optional — saved /ml/pipelines recipe
    processors:           # optional inline overlay
      - class: WinsorizeByQuantile
        module_path: aqp.ml.processors
        kwargs: {lower_q: 0.01, upper_q: 0.99}
    fit: true
```

### Specialized convenience nodes

Each maps onto a single processor and shows up in the Manifest Builder
palette as its own tile:

| Node name | Processor |
| --- | --- |
| ``transform.ml_scale`` | `SklearnTransformerProcessor` (Standard / Robust / MinMax) |
| ``transform.ml_winsorize`` | `WinsorizeByQuantile` |
| ``transform.ml_lag_features`` | `LagFeatureGenerator` |
| ``transform.ml_rolling_features`` | `RollingFeatureGenerator` |
| ``transform.ml_seasonal_decompose`` | `SeasonalDecomposeFeatures` |
| ``transform.ml_pyod_outliers`` | `PyODOutlierFilter` |
| ``transform.ml_imputation`` | `Fillna` |
| ``transform.ml_target_encode`` | `TargetEncode` |

## Sink — `sink.ml_feature_snapshot`

Iceberg writer that stamps the resulting table with
``pipeline_recipe_id``, ``dataset_version_id``, and a stable
``feature_snapshot_id`` so downstream training runs can reload exactly
the same preprocessed features:

```yaml
- name: sink.ml_feature_snapshot
  kwargs:
    namespace: ml.features
    table: alpha_panel_v1
    pipeline_recipe_id: 1c5b...
    dataset_version_id: 9f8a...
    mode: append
```

The sink's result includes a ``feature_snapshot_id`` UUID; persist it
in the dataset registry so future ``DatasetH`` instances can lazily
reload from the snapshot table.

## End-to-end flow

```mermaid
graph LR
    Source[source.iceberg<br/>ohlcv] --> Recipe["transform.ml_preprocessing<br/>(saved recipe_id)"]
    Recipe --> Snap["sink.ml_feature_snapshot<br/>(ml.features.alpha_panel_v1)"]
    Snap --> Train[Experiment training<br/>reuses snapshot]
    Train --> Deploy[ModelDeployment]
    Deploy --> Live[DeployedModelAlpha<br/>online inference]
```

## REST

```bash
# Materialise a saved recipe into a manifest fragment for the
# Pipeline Builder UI.
curl -XPOST http://localhost:8000/ml/pipelines/<recipe_id>/as-node \
  -d '{"fit": false}' -H 'content-type: application/json'
```

Returns:

```json
{
  "name": "transform.ml_preprocessing",
  "label": "my-recipe",
  "enabled": true,
  "kwargs": {"recipe_id": "<recipe_id>", "fit": false}
}
```
