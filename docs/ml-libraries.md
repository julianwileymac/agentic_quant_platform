# ML library reference

> Per-framework reference for every model wrapper under
> [`aqp/ml/models/`](../aqp/ml/models/). Configs live under
> [`configs/ml/`](../configs/ml/).

## Coverage matrix

| Library | Wrapper(s) | Optional extra | Example config |
| --- | --- | --- | --- |
| scikit-learn | `SklearnRegressorModel`, `SklearnClassifierModel`, `SklearnPipelineModel`, `SklearnStackingModel`, `SklearnAutoPipelineModel` | `ml` | [sklearn_ridge_alpha.yaml](../configs/ml/frameworks/sklearn_ridge_alpha.yaml), [sklearn_stacking_alpha.yaml](../configs/ml/frameworks/sklearn_stacking_alpha.yaml) |
| LightGBM | `LGBModel` | `ml` | [alpha158_lgbm.yaml](../configs/ml/alpha158_lgbm.yaml) |
| XGBoost | `XGBModel` | `ml` | (in tree zoo) |
| CatBoost | `CatBoostModel` | `ml` | (in tree zoo) |
| Keras 3 | `KerasMLPModel`, `KerasLSTMModel`, `KerasFunctionalModel`, `KerasTabTransformerModel` | `ml-keras` | [keras_mlp_alpha.yaml](../configs/ml/frameworks/keras_mlp_alpha.yaml), [keras_tab_transformer.yaml](../configs/ml/frameworks/keras_tab_transformer.yaml) |
| TensorFlow native | `TFEstimatorModel` (linear / DNN / boosted_trees) | `ml-tensorflow` + `AQP_TF_NATIVE_ENABLED=true` | [tf_estimator_dnn.yaml](../configs/ml/frameworks/tf_estimator_dnn.yaml) |
| PyTorch (qlib ports) | `LSTMTSModel`, `TransformerTSModel`, `TCNTSModel`, `TabNetModel`, `HISTModel`, `GATsModel`, `TRAModel`, … | `ml-torch` | [alpha360_*.yaml](../configs/ml/) |
| Prophet | `ProphetForecastModel` | `ml-forecast` | [prophet_forecast_alpha.yaml](../configs/ml/frameworks/prophet_forecast_alpha.yaml) |
| sktime | `SktimeForecastModel`, `SktimeReductionForecastModel`, `AutoETSForecastModel`, `AutoARIMAForecastModel`, `ThetaForecastModel`, `BatsTbatsForecastModel` | `ml-forecast` | [sktime_reduction_forecast.yaml](../configs/ml/frameworks/sktime_reduction_forecast.yaml), [auto_ets_forecast.yaml](../configs/ml/frameworks/auto_ets_forecast.yaml), [auto_arima_forecast.yaml](../configs/ml/frameworks/auto_arima_forecast.yaml), [theta_forecast.yaml](../configs/ml/frameworks/theta_forecast.yaml) |
| PyOD | `PyODAnomalyModel` (iforest / knn / ecod / copod / lof / suod / auto_encoder / hbos / mcd / ocsvm / pca) | `ml-anomaly` | [pyod_anomaly_alpha.yaml](../configs/ml/frameworks/pyod_anomaly_alpha.yaml), [pyod_ecod_anomaly.yaml](../configs/ml/frameworks/pyod_ecod_anomaly.yaml) |
| HuggingFace transformers | `HuggingFaceTextSignalModel`, `HuggingFaceFinBertSentimentModel`, `HuggingFaceTimeSeriesModel`, `HuggingFaceGenerativeForecastModel` | `ml-transformers` (+ `AQP_HF_TIMESERIES_ENABLED=true` for time-series) | [huggingface_finbert_signal.yaml](../configs/ml/frameworks/huggingface_finbert_signal.yaml), [hf_finbert_sentiment.yaml](../configs/ml/frameworks/hf_finbert_sentiment.yaml), [hf_patchtst_forecast.yaml](../configs/ml/frameworks/hf_patchtst_forecast.yaml) |

## Adhoc / notebook surface

[`aqp.ml.adhoc`](../aqp/ml/adhoc/__init__.py) exposes a `quick_*`
namespace for one-off analyses without spelling out a full
`Experiment` config:

```python
from aqp.ml.adhoc import (
    quick_arima,
    quick_ecod,
    quick_finbert_sentiment,
    quick_iforest,
    quick_panel_fixed_effects,
    quick_prophet,
    quick_ridge,
    quick_text_embed,
    quick_theta,
)

# Linear / ridge / elasticnet
ridge = quick_ridge(features_df, target_series, alpha=1.0)
print(ridge.score, ridge.coefficients)

# Anomaly detection
iforest = quick_iforest(features_df, contamination=0.05)
print(iforest.n_anomalies)

# Forecasting
arima = quick_arima(series, horizon=10, order=(1, 1, 1))
prophet = quick_prophet(series, horizon=10)
theta = quick_theta(series, horizon=10)

# Embeddings & sentiment
embeds = quick_text_embed(headlines)
sentiment = quick_finbert_sentiment(headlines)

# Panel diagnostics
fe = quick_panel_fixed_effects(panel, target_col="y", entity_col="vt_symbol")
```

## Where to add a new wrapper

1. Implement the class under `aqp/ml/models/<library>.py`,
   subclassing [`Model`](../aqp/ml/base.py).
2. Decorate with `@register("Name", kind="model")` from
   [`aqp.core.registry`](../aqp/core/registry.py).
3. Make optional imports lazy (raise `RuntimeError` mentioning the
   right extra) so the rest of the registry keeps working.
4. Add a YAML under `configs/ml/frameworks/`.
5. Add a hermetic test under `tests/ml/models/` that monkey-patches
   the optional dep when needed.
6. Cross-list it here.

See [`docs/ml-framework.md`](ml-framework.md) for the full registry +
`Experiment` contract.
