# akquant-main/examples — Extraction Reference

**Source:** `inspiration/akquant-main/examples/`
**Repo character:** Hybrid Rust+Python backtester with rich examples. We do NOT import `akquant`; we mirror patterns into AQP equivalents.

## Strategies (12) — port to `aqp/strategies/akquant/`

### DualMovingAverageStrategy

**Source:** `strategies/01_stock_dual_moving_average.py` (and `02_parameter_optimization.py`, `12_wfo_integrated.py`)
**Class:** `DualMovingAverageStrategy`
**Logic:** Standard SMA fast/slow crossover.
**AQP target:** `aqp/strategies/akquant/dual_ma.py::DualMovingAverageAlpha`.
**Params:** `fast_window=5`, `slow_window=20`.

```python
class DualMovingAverageAlpha(IAlphaModel):
    def __init__(self, fast_window=5, slow_window=20):
        self.fast = fast_window
        self.slow = slow_window

    def generate_signals(self, bars, universe, context):
        signals = []
        for sym in universe:
            sub = bars[bars["vt_symbol"] == sym.vt_symbol]
            if len(sub) < self.slow:
                continue
            close = sub["close"]
            fast = close.rolling(self.fast).mean().iloc[-1]
            slow = close.rolling(self.slow).mean().iloc[-1]
            direction = 1 if fast > slow else -1 if fast < slow else 0
            if direction != 0:
                signals.append(Signal(symbol=sym, direction=direction, score=abs(fast/slow - 1)))
        return signals
```

### GridTradingStrategy

**Source:** `strategies/02_stock_grid_trading.py`
**Logic:** Grid layering around price; buy each lower grid level, sell at higher.
**AQP target:** `aqp/strategies/akquant/grid_trading.py::GridTradingStrategy` (full IStrategy due to grid state).
**Params:** `grid_step_pct=0.02`, `n_levels=5`, `qty_per_level=10`.

### AtrBreakoutStrategy

**Source:** `strategies/03_stock_atr_breakout.py`
**Logic:** Donchian-style breakout sized by ATR.
**AQP target:** `aqp/strategies/akquant/atr_breakout.py::AtrBreakoutAlpha`.

### MomentumRotationStrategy

**Source:** `strategies/04_stock_momentum_rotation.py`
**Logic:** Rank N tickers by trailing return; rotate into top-K each period.
**AQP target:** `aqp/strategies/akquant/momentum_rotation.py::MomentumRotationAlpha`.

### BucketMomentumRotationStrategy

**Source:** `strategies/06_stock_momentum_rotation_bucket.py`
**Logic:** Bucketed momentum — rank within sector buckets first.
**AQP target:** `aqp/strategies/akquant/bucket_momentum_rotation.py::BucketMomentumRotationAlpha`.

### TimerMomentumRotationStrategy

**Source:** `strategies/05_stock_momentum_rotation_timer.py`
**Logic:** Momentum rotation on a fixed timer (rebalance once per period only).
**AQP target:** `aqp/strategies/akquant/timer_momentum_rotation.py::TimerMomentumRotationAlpha`.

### TPlusOneStrategy

**Source:** `textbook/ch06_stock_a.py`
**Logic:** China T+1 settlement — bought today cannot be sold today; explicit holding-day check.
**AQP target:** `aqp/strategies/akquant/t_plus_one.py::TPlusOneStrategy`.

### FuturesTrendStrategy

**Source:** `textbook/ch07_futures.py`
**Logic:** Trend following on futures; explicit margin/contract handling.
**AQP target:** `aqp/strategies/akquant/futures_trend.py::FuturesTrendAlpha`.

### CoveredCallStrategy

**Source:** `textbook/ch08_options.py`
**Logic:** Hold underlying + sell covered calls; roll on expiry.
**AQP target:** `aqp/strategies/akquant/covered_call.py::CoveredCallStrategy`.

### ETFGridStrategy

**Source:** `textbook/ch09_funds.py`
**Logic:** ETF-specific grid trading.
**AQP target:** `aqp/strategies/akquant/etf_grid.py::ETFGridStrategy`.

### SixtyFortyRebalanceStrategy

**Source:** `textbook/ch09_portfolio.py`
**Logic:** 60% equity / 40% bond rebalance via `order_target_value`.
**AQP target:** `aqp/strategies/akquant/sixty_forty.py::SixtyFortyRebalanceStrategy`. Uses `aqp/strategies/portfolio_construction.py::SixtyForty`.

### TargetWeightsRebalance

**Source:** `43_target_weights_rebalance.py`
**Logic:** Explicit fixed weights across symbols; rebalance to targets each period.
**AQP target:** `aqp/strategies/akquant/target_weights.py::TargetWeightsRebalanceStrategy`. Uses `aqp/strategies/portfolio_construction.py::TargetWeightsRebalancer`.

## Notable utilities

### FactorEngine (Polars-based)

**Source:** `19_factor_expression.py`
**AQP target:** `aqp/data/factor_expression.py` (Phase 1 module).
**Implements:** `Ts_Mean`, `Ts_Std`, `Ts_Corr`, `Rank`, `Decay_Linear`, `Delta`. Tiny DSL parser.

```python
class FactorEngine:
    def evaluate(self, expr: str, df: pl.DataFrame) -> pl.Series:
        # parses Ts_Mean(close, 20), Rank(volume), etc.
        ...
```

### Walk-forward ML adapter

**Source:** `10_ml_walk_forward.py`, `pb_mock.py`
**AQP target:** `aqp/ml/walk_forward.py` (Phase 1 module).
**Pattern:** train on rolling window, predict on next, advance.

### Functional ML walk-forward

**Source:** `55_functional_ml_walk_forward.py`
**AQP mapping:** Same as above; functional callbacks become a `Trainer` class with `on_train_signal` hook.
