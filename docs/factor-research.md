# Factor Research

AQP ships an Alphalens-inspired factor evaluation pipeline plus the
purged / walk-forward cross-validators described in Lopez de Prado's
*Advances in Financial ML* and ML4T's utility module.

## One-liner evaluation

```python
from aqp.data.factors import evaluate_factor

report = evaluate_factor(
    factor=factor_df,        # long: timestamp, vt_symbol, factor
    prices=prices_df,        # long: timestamp, vt_symbol, close
    factor_name="my_factor",
    periods=(1, 5, 10, 21),
    n_quantiles=5,
)
report.ic_stats       # {"fwd_1": {"mean": ..., "ir": ..., ...}, ...}
report.cumulative_returns  # wide DataFrame: Q1..Q5
report.turnover       # Series: top-quantile daily rotation fraction
```

## UI

The **Factor Evaluation** page posts to ``POST /factors/evaluate`` which
enqueues a Celery task. The task logs the tear sheet to MLflow with tag
``aqp.component=factor_eval`` so every report is historically
comparable.

## Cross-validators

- :class:`aqp.data.cv.MultipleTimeSeriesCV` — rolling train/test on
  panel data, matches ML4T ``utils.MultipleTimeSeriesCV``.
- :class:`aqp.data.cv.PurgedKFold` — k-fold with embargo days between
  the training window and the test fold boundary.
- :class:`aqp.data.cv.TimeSeriesWalkForward` — rolling or expanding
  train windows with a fixed test-step cadence.

## ML alphas

Two gradient-boosted alpha models drop directly into the framework:

- :class:`aqp.strategies.ml_alphas.XGBoostAlpha`
- :class:`aqp.strategies.ml_alphas.LightGBMAlpha`

Both accept a ``feature_specs`` list (passed through
:class:`aqp.data.indicators_zoo.IndicatorZoo`) and a ``model_path`` that
gets pickled after ``train()``. Training auto-logs to MLflow via the
:mod:`aqp.mlops.model_registry` helper and can then be loaded in
production by calling :func:`aqp.mlops.model_registry.load_alpha_path`.
