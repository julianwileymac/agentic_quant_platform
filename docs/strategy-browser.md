# Strategy Browser

The Strategy Browser is a dedicated Solara page at `/strategy-browser` that
exposes two complementary views of the strategy library:

1. **Saved strategies** — everything a user has persisted via
   `POST /strategies/` (the Strategy Development page). Filter by tag,
   status, name, or minimum Sharpe; click through for version history,
   recent tests, equity curves, and a deep link into the per-strategy
   MLflow experiment.
2. **Alpha catalog** — the code-available `IAlphaModel` classes (both
   ported TA strategies and the native ML model wrappers), their tags,
   and a list of reference YAMLs in `configs/strategies/` that instantiate
   each one. Handy for discovering what's available before saving your
   own.

## API surface

- `GET /strategies/browse?tag=&status=&query=&min_sharpe=`
  → list of enriched strategy rows with latest backtest metrics and the
  MLflow run id of the most recent run.
- `GET /strategies/browse/catalog`
  → every registered `IAlphaModel` class, its module path, tag list, and
  reference YAMLs under `configs/strategies/`.
- `GET /strategies/{id}/experiment`
  → experiment name (`strategy/<id[:8]>`), MLflow tracking URI, and up to
  50 linked `BacktestRun` rows.

## Strategy tags

Every new concrete alpha carries a module-level `STRATEGY_TAGS` tuple
(e.g. `("pattern", "mean-reversion", "quant-trading")`). `aqp.strategies
.list_strategy_tags()` aggregates the tuples across every class in
`aqp.strategies.__all__`, so the browser's tag filter reflects the code
without any duplicated metadata.

## MLflow wiring

When `run_backtest_from_config` is called with a `strategy_id`, the
underlying `log_backtest` helper uses
`experiment_name_for_strategy(strategy_id)` to pick the per-strategy
experiment (`strategy/<id[:8]>`) and also sets the `aqp.strategy_id` tag
on the run. After the backtest completes, the resulting MLflow run id is
written onto `BacktestRun.mlflow_run_id` so the browser can deep-link.

To prevent the generic Celery autolog signals from opening a parent
MLflow run for every backtest task (which would swallow the nested
`log_backtest` run), the `aqp.tasks.backtest_tasks.*` /
`aqp.tasks.paper_tasks.*` / `aqp.tasks.ml_tasks.*` / `aqp.tasks.factor_tasks.*`
task names are explicitly listed in
`aqp.mlops.autolog._AUTOLOG_SKIP_TASKS`.

## Ported strategy catalog

Shipped alphas (at 0.4):

| Alpha class                | Tags                                           | Reference recipe                          |
|----------------------------|------------------------------------------------|-------------------------------------------|
| `AwesomeOscillatorAlpha`   | momentum, oscillator, quant-trading            | `configs/strategies/awesome_oscillator.yaml` |
| `HeikinAshiAlpha`          | pattern, reversal, quant-trading               | `configs/strategies/heikin_ashi.yaml`     |
| `DualThrustAlpha`          | intraday, breakout, quant-trading              | `configs/strategies/dual_thrust.yaml`     |
| `ParabolicSARAlpha`        | trend, quant-trading                           | `configs/strategies/parabolic_sar.yaml`   |
| `LondonBreakoutAlpha`      | breakout, fx, quant-trading                    | `configs/strategies/london_breakout.yaml` |
| `BollingerWAlpha`          | pattern, mean-reversion, quant-trading         | `configs/strategies/bollinger_w.yaml`     |
| `ShootingStarAlpha`        | pattern, reversal, quant-trading               | `configs/strategies/shooting_star.yaml`   |
| `RsiPatternAlpha`          | pattern, mean-reversion, quant-trading         | `configs/strategies/rsi_pattern.yaml`     |
| `OilMoneyRegressionAlpha`  | statistical, mean-reversion, quant-trading     | `configs/strategies/oil_money.yaml`       |
| `SmaCross`                 | momentum, reference, backtesting.py            | `configs/strategies/sma_cross.yaml`       |
| `Sma4Cross`                | momentum, reference, backtesting.py            | `configs/strategies/sma4_cross.yaml`      |
| `TrailingATRAlpha`         | momentum, trailing-stop, reference             | `configs/strategies/trailing_atr.yaml`    |
| `BaseAlgoExample`          | reference, stock-analysis-engine               | `configs/strategies/base_algo_example.yaml` |

## ML Training page

A sibling Solara page at `/ml` — launch any `aqp.ml` training run from a
form (pick feature handler + model class + segments), stream progress
through the existing `/chat/stream/{task_id}` WebSocket, and see the
resulting `ModelVersion` rows.
