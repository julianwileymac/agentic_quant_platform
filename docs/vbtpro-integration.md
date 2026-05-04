# vectorbt-pro deep integration

> Doc map: [docs/index.md](index.md) · Engines overview: [docs/backtest-engines.md](backtest-engines.md).

vectorbt-pro is the **primary vectorised backtest engine** in AQP. The
integration lives under [aqp/backtest/vbtpro/](../aqp/backtest/vbtpro/) and
exposes the full vbt-pro surface (signals, orders, optimizer, callbacks,
splitter, param sweeps, IndicatorFactory). The legacy
[aqp/backtest/vectorbtpro_engine.py](../aqp/backtest/vectorbtpro_engine.py)
is now a 10-line delegate so YAML configs that reference its module path
continue to resolve to the new class.

## Hard constraint: Numba

vbt-pro's per-bar callbacks (`signal_func_nb`, `order_func_nb`,
`pre_segment_func_nb`, …) run inside Numba's JIT. **LLM agents and
Python ML models cannot run there.** Two supported patterns work around
this constraint:

1. **Precompute** (default) — agents/ML run before the simulation,
   producing wide-format `entries` / `exits` / `size` / `price`
   DataFrames. The decisions are baked in; vbt-pro consumes them as
   plain arrays.
2. **Per-window** (`Splitter.apply`) — Python (and therefore agents/ML)
   runs in the WFO loop between train and test windows. Each window's
   inner backtest is still vectorised.

For true per-bar agent dispatch use the event-driven engine and the
`AgentDispatcher` primitive — see
[docs/backtest-engines.md#agent--ml-components](backtest-engines.md#agent--ml-components).

## Engine modes

`VectorbtProEngine.run` routes through one of five constructors based on
the `mode` kwarg. All five share a common kwarg surface (initial_cash,
fees, slippage, freq, cash_sharing, group_by, leverage, multiplier,
direction, …) and merge any extra `portfolio_kwargs` into the call.

| Mode        | Constructor                       | Driver                                                | Use case                                              |
|-------------|-----------------------------------|-------------------------------------------------------|-------------------------------------------------------|
| `signals`   | `Portfolio.from_signals`          | `IAlphaModel` → wide entries/exits/(size)/(price)/(stops) | The default; mirrors classical signal-based backtests. |
| `orders`    | `Portfolio.from_orders`           | `IOrderModel` → wide size/price/size_type             | Agent-emitted precise orders; multi-leg sizing.       |
| `optimizer` | `Portfolio.from_optimizer`        | `PortfolioOptimizer` (mean-variance, risk parity, custom) | Allocation-driven research, no signal generation.    |
| `holding`   | `Portfolio.from_holding`          | —                                                     | Buy-and-hold sanity baseline.                         |
| `random`    | `Portfolio.from_random_signals`   | `Param`-style random kwargs                           | Null-hypothesis baseline.                             |

## Components

| File                                                      | Role                                                                            |
|-----------------------------------------------------------|---------------------------------------------------------------------------------|
| [`engine.py`](../aqp/backtest/vbtpro/engine.py)           | Multi-mode dispatch; `@register("VectorbtProEngine")`.                          |
| [`signal_builder.py`](../aqp/backtest/vbtpro/signal_builder.py) | `IAlphaModel` → `SignalArrays`; per-bar loop **and** `generate_panel_signals` opt-in. |
| [`order_builder.py`](../aqp/backtest/vbtpro/order_builder.py) | `IOrderModel` → `OrderArrays`; `signals_to_orders` sizer helper.            |
| [`optimizer_adapter.py`](../aqp/backtest/vbtpro/optimizer_adapter.py) | `EqualWeightOptimizer`, `MeanVarianceOptimizer`, `RandomWeightOptimizer`, `CallableOptimizer`; all decorated with `@register(..., kind="portfolio")`. |
| [`result_mapper.py`](../aqp/backtest/vbtpro/result_mapper.py) | `vbt.Portfolio` → `BacktestResult`; merges `vbt_*` native stats.            |
| [`wfo.py`](../aqp/backtest/vbtpro/wfo.py)                 | `WalkForwardHarness` + `PurgedWalkForwardHarness` driven by vbt-pro's `Splitter`. |
| [`param_sweep.py`](../aqp/backtest/vbtpro/param_sweep.py) | `sweep_strategy_kwargs` (grid/random) + `sweep_signals_grid` (`Param`-native MA cross). |
| [`indicator_factory_bridge.py`](../aqp/backtest/vbtpro/indicator_factory_bridge.py) | Wraps AQP `IndicatorBase` zoo entries as vbt-pro `IndicatorFactory` classes. |
| [`data_utils.py`](../aqp/backtest/vbtpro/data_utils.py)   | `pivot_close`, `pivot_ohlcv`, `universe_from_bars`, `filter_bars`.              |

## Agent + ML strategy components

| File                                                      | Class                  | Role                                                                  |
|-----------------------------------------------------------|------------------------|-----------------------------------------------------------------------|
| [`agentic_alpha.py`](../aqp/strategies/vbtpro/agentic_alpha.py) | `AgenticVbtAlpha`      | Precompute / per-window / live modes. Reads `DecisionCache` and renders to wide arrays. |
| [`ml_alpha.py`](../aqp/strategies/vbtpro/ml_alpha.py)     | `MLVbtAlpha`           | Wraps any `aqp.ml.base.Model` (or MLflow URI). Threshold / top-k / rank policies. |
| [`agent_order_model.py`](../aqp/strategies/vbtpro/agent_order_model.py) | `AgenticOrderModel` | Implements `IOrderModel`; drives the `orders` mode from cached agent decisions. |

Each component is `@register`-ed so it can be dropped into a strategy
YAML via the standard `class` / `module_path` / `kwargs` factory.

## Walk-forward optimisation

```python
from aqp.backtest.vbtpro.wfo import WalkForwardHarness

harness = WalkForwardHarness(
    strategy_cfg={"class": "FrameworkAlgorithm", "module_path": "...", "kwargs": {...}},
    splitter="rolling",   # or "expanding", "purged"
    n_splits=8,
    train_size=504,
    test_size=126,
    engine_kwargs={"mode": "signals", "initial_cash": 100_000.0},
    on_window_train=lambda i, slice_, strategy, ctx: warm_agent(strategy, slice_),
)
result = harness.run(bars)
```

The harness re-instantiates the strategy on every window (so per-window
agent state is isolated), runs the train backtest, then re-instantiates
again before the test pass. The optional `on_window_train` hook is where
agents refresh their RAG / memory or ML models refit.

`PurgedWalkForwardHarness` defaults `splitter="purged"` and uses
`PurgedWalkForwardCV` from `vectorbtpro.generic.splitting.purged` to drop
labels that bleed across the train/test boundary.

## Parameter sweeps

```python
from aqp.backtest.vbtpro.param_sweep import sweep_strategy_kwargs

result = sweep_strategy_kwargs(
    base_config,
    {
        "strategy.kwargs.alpha_model.kwargs.fast": [5, 10, 20],
        "strategy.kwargs.alpha_model.kwargs.slow": [50, 100, 200],
    },
    metric="sharpe",
    method="grid",
)
print(result.best_combo, result.best_value)
print(result.frame.head())
```

Random sweeps require `n_trials`. Trials default to running with
`engine: vbt-pro:signals` if the base config does not specify one.
`sweep_signals_grid` is the fast `Param`-native path for single-symbol
MA-crossover style sweeps.

## Indicator factory bridge

```python
from aqp.backtest.vbtpro.indicator_factory_bridge import vbt_indicator

SMA = vbt_indicator("SMA")
out = SMA.run(close, period=[10, 20, 50])  # vbt.Param under the hood
sma_50 = out.value[(slice(None), 50)]
```

This makes every AQP `IndicatorBase` available inside vbt-pro's
indicator/sweep machinery without rewriting the underlying state machine.

## Agent tools

| Tool name                  | Class                       | Surface                                       |
|----------------------------|-----------------------------|-----------------------------------------------|
| `vectorbt_pro_backtest`    | `VectorbtProBacktestTool`   | One backtest, explicit mode.                  |
| `vectorbt_pro_param_sweep` | `VbtProParamSweepTool`      | Grid / random sweep over strategy kwargs.     |
| `vectorbt_pro_wfo`         | `VbtProWalkForwardTool`     | Splitter-WFO; rolling/expanding/purged.       |
| `vectorbt_pro_optimizer`   | `VbtProOptimizerTool`       | Allocation-driven via `Portfolio.from_optimizer`. |
| `engine_capabilities`      | `EngineCapabilitiesTool`    | Inspect the capability matrix; pick an engine.|
| `agent_aware_backtest`     | `AgentAwareBacktestTool`    | Run `AgentAwareMomentumAlpha` on the event-driven engine. |

All tools are registered in `aqp.agents.tools.TOOL_REGISTRY` and
referenced in [configs/agents/quant_research_vbtpro.yaml](../configs/agents/quant_research_vbtpro.yaml).

## Example configs

- [configs/strategies/vbtpro/dual_ma_signals.yaml](../configs/strategies/vbtpro/dual_ma_signals.yaml)
  — minimal `signals` mode example.
- [configs/strategies/vbtpro/agentic_trader.yaml](../configs/strategies/vbtpro/agentic_trader.yaml)
  — `AgenticVbtAlpha` precompute.
- [configs/strategies/vbtpro/ml_topk.yaml](../configs/strategies/vbtpro/ml_topk.yaml)
  — `MLVbtAlpha` top-k.
- [configs/strategies/vbtpro/wfo_agentic.yaml](../configs/strategies/vbtpro/wfo_agentic.yaml)
  — per-window agent dispatch.
- [configs/strategies/vbtpro/optimizer_meanvariance.yaml](../configs/strategies/vbtpro/optimizer_meanvariance.yaml)
  — allocation-only optimizer mode.

## Performance notes

- **Default Numba JIT** is ON. The first vbt-pro call in a fresh process
  pays a non-trivial compile cost (~10-30s for the full surface). Cache
  ahead of time on workers if latency matters.
- **`jitted=False`** swaps the outer simulation wrapper to a Python
  reference implementation; it does not let arbitrary Python live inside
  `signal_func_nb`. Use precompute or per-window for that.
- The `IndicatorFactory` bridge applies AQP indicators per column in pure
  Python, which is slow for very wide universes; for hot paths prefer
  vbt-pro's native indicators (`vbt.SMA`, `vbt.RSI`, etc.) and only fall
  back to the bridge for indicators we don't have a vbt-pro analogue for.

## Migration from the legacy adapter

The previous `VectorbtProEngine` only handled signals via
`IAlphaModel.generate_signals` → `Portfolio.from_signals`. Existing
configs still work because:

- The legacy module path
  `aqp.backtest.vectorbtpro_engine.VectorbtProEngine` re-exports the new
  class.
- The default mode is still `signals`.
- Existing kwargs (`initial_cash`, `fees`, `slippage`, `allow_short`,
  `freq`, `group_by`) are unchanged in meaning.

New kwargs that gate richer behaviour: `mode`, `direction`, `accumulate`,
`size`, `size_type`, `sl_stop`, `tsl_stop`, `tp_stop`, `leverage`,
`leverage_mode`, `multiplier`, `cash_sharing`, `portfolio_kwargs`,
`order_model`, `optimizer`, `random_kwargs`, `record_signals`.
