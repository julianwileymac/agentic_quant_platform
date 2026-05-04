# FinRL-Trading-master - Extraction Reference

**Source:** `inspiration/FinRL-Trading-master/`
**Repo character:** Weight-centric modular stack (data -> strategy -> backtest -> execution) with ML stock selection, DRL allocation, adaptive rotation, and live Alpaca-oriented components.

## Strategy and RL ports

### MLStockSelectionAlpha

**Source:** `src/strategies/ml_strategy.py`
**Logic:** Train regression/classification model on factor panel and rank symbols by predicted return.
**AQP target:** `aqp/strategies/ml_selection.py::MLStockSelectionAlpha`

### SectorNeutralMLAlpha

**Source:** `src/strategies/ml_bucket_selection.py`
**Logic:** Bucket-aware stock selection to reduce sector concentration.
**AQP target:** `aqp/strategies/ml_selection.py::SectorNeutralMLAlpha`

### AdaptiveRotationAlpha

**Source:** `src/strategies/adaptive_rotation/*`
**Logic:** Regime-aware bucket rotation with momentum ranking and risk overlays.
**AQP target:** `aqp/strategies/adaptive_rotation/rotation_alpha.py::AdaptiveRotationAlpha`

### GICSBucketUniverseSelector

**Source:** `src/strategies/group_selection_by_gics.py` and adaptive rotation universe logic
**Logic:** Group symbols by GICS-derived buckets before ranking/allocation.
**AQP target:** `aqp/strategies/adaptive_rotation/gics_buckets.py::GICSBucketUniverseSelector`

### MarketRegimeClassifier

**Source:** `src/strategies/adaptive_rotation/market_regime.py`
**Logic:** Slow/fast market risk regime switching.
**AQP target:** `aqp/strategies/regime_detection.py` and `aqp/strategies/adaptive_rotation/market_regime.py`

### Fundamental portfolio DRL facade

**Source:** `src/strategies/fundamental_portfolio_drl.py` + `src/strategies/rl_model.py`
**Logic:** DRL allocator with optional post-allocation portfolio shaping.
**AQP target:** `aqp/rl/applications/fundamental_portfolio_drl.py::train_fundamental_portfolio_drl`

## Model and training patterns

### Per-window RL train/test rollout

**Source:** `src/strategies/rl_model.py`
**Pattern:** Rolling training window + holdout test window around a trade date.
**AQP target:** `aqp/ml/walk_forward.py`, `aqp/ml/splits.py`, and RL app wiring under `aqp/rl/`

### Point-in-time quarterly split

**Source:** `src/strategies/ml_bucket_selection.py` and `ML_STOCK_SELECTION.md`
**Pattern:** Datadate -> tradedate mapping and train/validation/inference segmentation with membership filtering.
**AQP target:** `aqp/ml/splits.py` and dataset preset sample loaders

```python
train = frame[frame[date_col] < train_end]
valid = frame[(frame[date_col] >= train_end) & (frame[date_col] < infer_date)]
infer = frame[frame[date_col] == infer_date]
```

## Data and preprocessing extraction

### Fundamental panel + y_return semantics

**Source:** `ML_STOCK_SELECTION.md`, `src/data/fetch_and_store_fundamentals.py`
**Pattern:** Log-return target on tradedate prices, strict no-lookahead handling.
**AQP target:** dataset preset pipelines + helper split/validation utilities

### Feature normalization and panel prep

**Source:** `src/data/data_processor.py`, `src/strategies/adaptive_rotation/data_preprocessor.py`
**Pattern:** Missing-value fill, robust scaling, calendar alignment, per-symbol feature prep.
**AQP target:** `aqp/ml/processors.py` and dataset preset pipelines

## Backtesting and evaluation patterns

### Weight-centric backtest summary

**Source:** `src/backtest/backtest_engine.py`, `src/trading/performance_analyzer.py`
**Pattern:** Unified metrics (`total_return`, `annual_return`, `annual_volatility`, `sharpe`, `sortino`, `max_drawdown`) with benchmark comparison.
**AQP target:** `aqp/backtest/metrics.py`, `aqp/backtest/vbtpro/result_mapper.py`

## Dataset/pipeline extraction opportunities

### FinRL sample presets

High-value sample datasets to expose via one-click presets:

1. Fundamental panel sample (`data/fundamental_data_full.csv`)
2. SP500 historical membership sample (`data/sp500_historical_constituents.csv`)

**AQP target:** `aqp/data/dataset_presets.py` + `aqp/data/pipelines/dataset_preset_pipelines.py`

## Caveats

- Full upstream parity may require optional heavy dependencies (`torch`, `finrl`, `stable-baselines3`, `gymnasium`).
- Several flows rely on external data/providers and API keys.
- Live trading components are Alpaca-centric and should remain optional in AQP.
