# AQP Inspiration Extraction Index

> Reference cache for the rehydration of AQP from 9 inspiration sources.
> **Use these markdown files instead of re-reading the raw inspiration code.**
> Each per-source `REFERENCE.md` contains the extracted code excerpts and AQP mapping notes.

## Sources

| Source folder | Source repo (under `inspiration/`) | Reference doc | Asset count |
|---------------|------------------------------------|---------------|-------------|
| `stock_analysis_engine/` | `stock-analysis-engine-master/analysis_engine` | [REFERENCE.md](stock_analysis_engine/REFERENCE.md) | 13 |
| `analyzingalpha/` | `analyzingalpha-master` | [REFERENCE.md](analyzingalpha/REFERENCE.md) | 18 |
| `quant_trading/` | `quant-trading-master` | [REFERENCE.md](quant_trading/REFERENCE.md) | 15 |
| `finrl_trading/` | `FinRL-Trading-master` | [REFERENCE.md](finrl_trading/REFERENCE.md) | 12 |
| `notebooks/` | `notebooks-master` | [REFERENCE.md](notebooks/REFERENCE.md) | 17 |
| `akquant/` | `akquant-main/examples` | [REFERENCE.md](akquant/REFERENCE.md) | 60+ |
| `qtradex/` | `QTradeX-AI-Agents-master` | [REFERENCE.md](qtradex/REFERENCE.md) | 28 |
| `hftbacktest/` | `hftbacktest-master/examples` | [REFERENCE.md](hftbacktest/REFERENCE.md) | 19 |
| `stock_prediction_models/` | `Stock-Prediction-Models-master` | [REFERENCE.md](stock_prediction_models/REFERENCE.md) | 22 |

## Cross-cutting docs

- [_KNOWN_ISSUES.md](_KNOWN_ISSUES.md) — items deliberately not fixed; trade-offs.
- [_FUTURE_PROMPTS/lob_adapter_prompt.md](_FUTURE_PROMPTS/lob_adapter_prompt.md) — itemized prompt for the deferred hftbacktest LOB adapter.

## Canonical platform smoke runs (from Phase 10)

These three random end-to-end tests exercise the rehydrated platform across every layer:

1. **Strategy backtest** — `tests/strategies/test_ma_sabres_backtest.py` (QTradeX `MASabres` via `EventDrivenBacktester`).
2. **ML training** — `tests/ml/models/test_lstm_forecaster_train.py` (SPM `LSTMForecaster` via `TorchForecasterBase` + `WalkForwardTrainer`).
3. **Agent run** — `tests/agents/test_regime_analyst_run.py` (new `research.regime_analyst` spec via `AgentRuntime`).

## Four-source backend hydration smoke runs

Deterministic random seed (`20260503`) selection across strategy/model/pipeline surfaces:

1. **Strategy smoke** — `tests/strategies/test_four_source_random_strategy_smoke.py`.
2. **Model smoke** — `tests/ml/models/test_four_source_random_model_smoke.py`.
3. **Pipeline smoke** — `tests/data/test_four_source_random_pipeline_smoke.py`.

## How to use this cache

When extending or debugging an extracted asset:
1. Open the per-source `REFERENCE.md`.
2. Find the asset section (`## <AssetName>`).
3. Each section lists: source path, key excerpt, AQP target file, refactor notes, dependencies, gotchas.
4. Cross-check the live AQP module under the proposed target path.

When adding a new asset from one of these sources, append a new `## <AssetName>` section at the bottom of the relevant `REFERENCE.md`.

## Final rehydration tally

After completion of the 13-phase plan:

| Surface | Total registered | Notes |
|---------|------------------|-------|
| Strategies | **75** | qtradex 27 + notebooks 20 + akquant 12 + analyzingalpha 8 + sae 3 + hft 5 (engine pending) |
| ML forecasters/classifiers | **18** | SPM forecasters 14 + SPM classical 4 + notebooks 2 (RidgeVoC, LogisticWalkForward) + sae 1 (KerasMLPRegressor) |
| RL agents | **4 net-new + ~9 re-tagged** | DoubleDuelingDQN, A3C, PolicyGradient, ActorCriticExperienceReplay (new); existing q_family/actor_critic/evolutionary classes re-tagged with `source:stock_prediction_models` |
| Indicators | **15 added** | KST, RAVI, FRAMA, Vortex, Fisher, UlcerIndex, Coppock, MassIndex, MesaSineWave, Renko, ZigZag, AnchoredVWAP, OFI, Microprice, DepthSlope (47 total ALL_INDICATORS) |
| Tools | **9 added** | cointegration_tool, regime_classifier_tool, realised_vol_tool, factor_screen_tool, hft_metrics_tool, multi_indicator_vote_tool, chart_pattern_tool, option_greeks_tool, option_spread_tool (36 total in TOOL_REGISTRY) |
| Agent specs | **9 added** | research.{regime_analyst, composite_voter, basis_momentum_analyst, cointegration_analyst, intraday_momentum_analyst, options_greeks_explainer}, selection.cross_asset_skew_screener, analysis.{queue_position_analyst, cointegration_basket_finder} |
| Dataset presets | **8** | intraday_momentum_etf, commodity_futures_panel, china_a_shares_top200, crypto_majors_intraday, equity_universe_sp500_daily, fred_macro_basket, eod_options_chain_sample, lob_btcusdt_sample |
| Risk models added | **2** | VolTargetingRiskModel, MaxNotionalPerSymbolRiskModel |
| Portfolio construction added | **5** | TargetWeightsRebalancer, MomentumRotationConstruction, SixtyForty, BasicRiskParity, BasicHRP |
| New framework modules | **15** | aqp/data/{microstructure, realised_volatility, cointegration, regime, labels, factor_expression, spread_models, patterns}.py + aqp/options/{normal_model, inverse_options, spreads}.py + aqp/strategies/{portfolio_construction, lob}.py + aqp/backtest/hft_metrics.py + aqp/ml/{walk_forward, models/spm/_torch_base}.py |
| New UI pages | **6** | /ml/zoo, /rl/zoo, /agents/templates, /data/datasets/library, /data/microstructure, /options/lab |
| New API routes | **1** | /dataset-presets |
| New Celery tasks | **9** | dataset_preset_tasks (one per preset) |
| Migrations | **1** | 0016_extraction_metadata.py |
| Tests | **3 files / 6 cases** | All passing — see canonical platform smoke runs above |

**Total registered assets**: ~140 across all surfaces. **Total YAML configs added**: ~25 (representative — the config schema is uniform so users copy + swap class names).
