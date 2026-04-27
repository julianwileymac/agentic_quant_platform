# AQP × ML4T — Chapter 12 (Gradient Boosting Machines)

This folder mirrors [stefan-jansen/machine-learning-for-trading/12_gradient_boosting_machines](https://github.com/stefan-jansen/machine-learning-for-trading/tree/main/12_gradient_boosting_machines)
using the AQP framework (Alpha158 handler, `IndicatorZoo`, our LightGBM /
CatBoost / XGBoost wrappers, MLflow logging, and DuckDB-backed bars).

## Notebook map

| AQP notebook | Upstream notebook |
|--------------|-------------------|
| `01_boosting_baseline.ipynb` | 01_boosting_baseline |
| `02_sklearn_gbm_tuning.ipynb` | 02_sklearn_gbm_tuning |
| `03_sklearn_gbm_tuning_results.ipynb` | 03_sklearn_gbm_tuning_results |
| `04_preparing_the_model_data.ipynb` | 04_preparing_the_model_data |
| `05_trading_signals_with_lightgbm_and_catboost.ipynb` | 05_trading_signals_with_lightgbm_and_catboost |
| `06_evaluate_trading_signals.ipynb` | 06_evaluate_trading_signals |
| `07_model_interpretation.ipynb` | 07_model_interpretation |
| `08_making_out_of_sample_predictions.ipynb` | 08_making_out_of_sample_predictions |
| `09_backtesting_with_zipline.ipynb` | 09_backtesting_with_zipline (we use AQP backtest engine) |
| `10_intraday_features.ipynb` | 10_intraday_features |
| `11_intraday_model.ipynb` | 11_intraday_model |

## Pre-requisites

```bash
make ingest                         # populate DuckDB with daily SPY/AAPL/MSFT/...
pip install -e ".[ml,ml-torch]"     # LightGBM/XGBoost/CatBoost + torch
docker compose up -d mlflow         # tracking server
```

## Configs

All notebooks consume YAML recipes from `configs/ml/ml4t/`:

- `gbm_baseline.yaml`
- `sklearn_gbm_tuning.yaml`
- `lightgbm_signals.yaml`
- `catboost_signals.yaml`
- `intraday_gbm.yaml`

These YAMLs are also registered with the `/ml/recipes` API endpoint and
appear in the WebUI training page's "Recipe" dropdown.
