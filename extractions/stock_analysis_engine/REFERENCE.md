# stock-analysis-engine - Extraction Reference

**Source:** `inspiration/stock-analysis-engine-master/analysis_engine/`
**Repo character:** Redis/S3-backed pricing cache + indicator-centric algorithm runner + Celery work-task orchestration.

## Strategy and model ports

### StockAnalysisEngineAdapterStrategy

**Source:** `algo.py::BaseAlgo` and process callback conventions
**Logic:** Wrap custom per-bar `process` logic in a framework strategy shell.
**AQP target:** `aqp/strategies/sae/alphas.py::StockAnalysisEngineAdapterStrategy`

### IndicatorVoteAlpha

**Source:** `algo.py` vote-style indicator decisions
**Logic:** Consensus voting across indicator outputs with buy/sell thresholds.
**AQP target:** `aqp/strategies/sae/alphas.py::IndicatorVoteAlpha`

### OptionSpreadStrategy

**Source:** `build_option_spread_details.py`, `build_entry_call_spread_details.py`, `build_exit_call_spread_details.py`
**Logic:** Vertical spread setup and payoff-oriented option strategy scaffolding.
**AQP target:** `aqp/strategies/sae/alphas.py::OptionSpreadStrategy`

### KerasMLPRegressor

**Source:** `ai/build_regression_dnn.py`
**Logic:** Feed-forward MLP with scaler preprocessing for regression forecasts.
**AQP target:** `aqp/ml/models/sae/keras_mlp_regressor.py::KerasMLPRegressor`

## High-value utility extraction

### Option spread math

**Source:** `build_option_spread_details.py`
**AQP target:** `aqp/options/spreads.py`

```python
def vertical_spread_details(long_strike, short_strike, long_premium, short_premium):
    width = abs(long_strike - short_strike)
    net_debit = long_premium - short_premium
    max_profit = width - net_debit
    max_loss = net_debit
    return {"width": width, "net_debit": net_debit, "max_profit": max_profit, "max_loss": max_loss}
```

### Indicator processor bridge

**Source:** `indicators/indicator_processor.py`, `indicators/base_indicator.py`, `indicators/*.py`
**Logic:** Single pipeline for indicator registration, transform, and scoring.
**AQP mapping:** `aqp/data/indicators_zoo.py` and strategy-level indicator voting.

### Options expiration helper

**Source:** `options_dates.py`, `holidays.py`
**Logic:** Expiration and calendar-aware date calculations.
**AQP mapping:** utility-level options calendar support and options lab tooling.

## Data/pipeline extraction candidates

### Fetch/extract/cache pipeline

**Source:** `fetch.py`, `extract.py`, `load_dataset.py`, `prepare_history_dataset.py`, `dataset_scrub_utils.py`, `compress_data.py`
**Pattern:** Acquire, normalize, cache, and reload time-series datasets from Redis/S3.
**AQP mapping:** dataset presets + ingestion pipelines + Iceberg writes.

### Celery-style jobs

**Source:** `work_tasks/task_run_algo.py`, `work_tasks/get_new_pricing_data.py`, `work_tasks/prepare_pricing_dataset.py`, `work_tasks/run_distributed_algorithm.py`
**Pattern:** Task wrappers around fetch/run/publish loops.
**AQP mapping:** `aqp/tasks/*` with progress bus (`emit`, `emit_done`, `emit_error`).

### Scripted backtest workflows

**Source:** `scripts/backtest_with_runner.py`, `scripts/run_backtest_and_plot_history.py`, `scripts/train_dnn_from_history.py`
**Pattern:** CLI-friendly sample workflows for model training and strategy replay.
**AQP mapping:** sample configs in `configs/` and test fixtures under `tests/`.

## Caveats

- Native SAE runtime assumes Redis/S3-centric storage conventions; AQP uses Iceberg and Postgres as first-class state.
- Some sources depend on provider-specific APIs and tokens (`IEX`, `Tradier`, `Finviz`).
- Script/module APIs are not uniformly typed and often require adaptation to AQP's `Symbol` and framework contracts.
