# aqp_rl Current State — Phase 0 Recon

Source: live inspection of [aqp_rl/](../../aqp_rl/) on 2026-05-24.

This document is the ground-truth inventory consumed by Phase 1-12 of
[aqp-rl_production_enhancement_602200e2.plan.md](aqp-rl_production_enhancement_602200e2.plan.md).
Every Phase that follows asserts against capabilities flagged
**MISSING** or **PARTIAL** here.

## 1. Architecture skeleton — PRESENT

| Surface | File | Notes |
| --- | --- | --- |
| `RLComponent` metaclass | [src/aqp_rl/core/base.py](../../aqp_rl/src/aqp_rl/core/base.py) | 13 canonical `rl_kind` values (`rl_env`, `rl_reward`, `rl_observation`, `rl_action`, `rl_termination`, `rl_policy`, `rl_agent`, `rl_data`, `rl_ensembler`, `rl_experiment`, `rl_trajectory_store`, `rl_advantage_estimator`, `rl_policy_backbone`). Auto-registers via `aqp.core.registry.register`. |
| `RLExperimentSpec` | [src/aqp_rl/spec.py](../../aqp_rl/src/aqp_rl/spec.py) | Pydantic-v2 model. `snapshot_hash()` = SHA-256 of canonical JSON. Sub-specs: `UniverseRef`, `DataPipelineRef`, `TrainingConfig` (with `advantage` + `stop_properly_penalty_coef`), `EvaluationConfig`, `EnsemblerRef`, `TrajectoryStoreRef`, `MLflowConfig`, `RewardRef`, `ObservationRef`, `ActionRef`, `TerminationRef`. |
| `RLRuntime` | [src/aqp_rl/runtime.py](../../aqp_rl/src/aqp_rl/runtime.py) | Sole executor (rule 16). Public methods: `train`, `evaluate`, `paper`, `replay`, `walk_forward`. Persists `rl_experiment_versions` row + `rl_runs` row + per-step trajectory store. Emits progress via `aqp.tasks._progress.emit`. |
| `registry.persist_spec` | [src/aqp_rl/registry.py](../../aqp_rl/src/aqp_rl/registry.py) | Hash-locked snapshot to `rl_experiment_versions` (rule 17). YAML dir scan over `aqp_rl/configs/specs/` with legacy fallback to `configs/rl/specs/`. |
| `BaseRLEnv` | [src/aqp_rl/core/env.py](../../aqp_rl/src/aqp_rl/core/env.py) | `gym.Env + RLComponent`. Composable obs/action/reward/termination, Gymnasium 5-tuple step, auto-installs `StopProperlyWrapper` when spec sets coefficient. |
| `BaseRewardModel` + `RewardTerm` + `CompositeReward` | [src/aqp_rl/core/reward.py](../../aqp_rl/src/aqp_rl/core/reward.py) | Decomposition published to `info["reward_terms"]` for the Iceberg `rl.reward_decomposition` table. |
| `BaseObservationBuilder` + `StackedObservationBuilder` | [src/aqp_rl/core/observation.py](../../aqp_rl/src/aqp_rl/core/observation.py) | Stack along axis 0; `feature_names()` for UI; NaN/Inf scrubbed. |
| `BaseActionSpace` | [src/aqp_rl/core/action.py](../../aqp_rl/src/aqp_rl/core/action.py) | Ships 6 concrete spaces (Continuous, Softmax, IntegerShares, Discrete, MultiDiscrete, TargetPosition). |
| `BaseTerminationCondition` | [src/aqp_rl/core/termination.py](../../aqp_rl/src/aqp_rl/core/termination.py) | `truncates_episode` flag for FinRL-X "stop properly". |
| `BaseTrajectoryStore` + `InMemoryTrajectoryStore` | [src/aqp_rl/core/replay.py](../../aqp_rl/src/aqp_rl/core/replay.py) | Rule 18 contract. `BaseReplayBuffer` ABC + `InMemoryReplayBuffer` (deque FIFO). |
| `IcebergTrajectoryStore` | [src/aqp_rl/trajectories/iceberg_writer.py](../../aqp_rl/src/aqp_rl/trajectories/iceberg_writer.py) | Buffers Arrow rows, flushes via `iceberg_catalog.append_arrow`. Tables: `rl.trajectories`, `rl.equity_curves`, `rl.action_logs`, `rl.reward_decomposition`. |
| `WeightCentricPipeline` (`f_S -> f_A -> f_T -> f_R`) | [src/aqp_rl/portfolio/pipeline.py](../../aqp_rl/src/aqp_rl/portfolio/pipeline.py) | Rule 38. `PipelineState.history` records per-stage snapshots. |
| `WeightToOrders` + `apply_target_weights` | [src/aqp_rl/execution/weight_to_orders.py](../../aqp_rl/src/aqp_rl/execution/weight_to_orders.py) | Async, kill-switch gated via `aqp.risk.kill_switch.is_engaged`, rebalance threshold default 50 bps. Emits `MarketOrder` via `aqp.core.domain.orders`. |
| `LLMHybridAgent` | [src/aqp_rl/agents/llm_hybrid.py](../../aqp_rl/src/aqp_rl/agents/llm_hybrid.py) | Rule 20: routes through `aqp.llm.providers.router.router_complete`. JSON-action protocol; weighted blending with RL backbone. |

## 2. Rewards — what exists

[src/aqp_rl/rewards/](../../aqp_rl/src/aqp_rl/rewards/) currently ships:

| Class | File | Notes |
| --- | --- | --- |
| `PnLTerm` | [pnl.py](../../aqp_rl/src/aqp_rl/rewards/pnl.py) | `pv_t - pv_{t-1}` × scale |
| `LogReturnTerm` | [pnl.py](../../aqp_rl/src/aqp_rl/rewards/pnl.py) | `log(pv_t / pv_{t-1})` |
| `DrawdownPenaltyTerm` | [risk.py](../../aqp_rl/src/aqp_rl/rewards/risk.py) | reads `info["drawdown"]` |
| `VolatilityPenaltyTerm` | [risk.py](../../aqp_rl/src/aqp_rl/rewards/risk.py) | rolling stdev penalty |
| `SharpeTerm` | [risk.py](../../aqp_rl/src/aqp_rl/rewards/risk.py) | **rolling** (episode-level) Sharpe — NOT differential per-step |
| `SortinoTerm` | [risk.py](../../aqp_rl/src/aqp_rl/rewards/risk.py) | **rolling** Sortino — NOT differential per-step |
| `TurnoverPenaltyTerm` / `TransactionCostTerm` / `SlippagePenaltyTerm` | [cost.py](../../aqp_rl/src/aqp_rl/rewards/cost.py) | turnover-weighted penalties |
| `CashIdlePenaltyTerm` / `BenchmarkOutperformanceTerm` / `RiskParityTerm` | [constraint.py](../../aqp_rl/src/aqp_rl/rewards/constraint.py) | behavioural shaping |
| `TurbulenceGateTerm` / `MarginCallTerm` | [gating.py](../../aqp_rl/src/aqp_rl/rewards/gating.py) | risk-state gates |
| `InventoryQuadraticPenaltyTerm` | [inventory_quadratic.py](../../aqp_rl/src/aqp_rl/rewards/inventory_quadratic.py) | `-phi * q^2` (Cartea-Jaimungal partial — running term only, no terminal) |
| `PotentialBasedShaping` | [shaping.py](../../aqp_rl/src/aqp_rl/rewards/shaping.py) | Ng et al. 1999 |
| `StopProperlyPenaltyTerm` / `StopProperlyWrapper` | [stop_properly.py](../../aqp_rl/src/aqp_rl/rewards/stop_properly.py) | NeMo-RL truncation penalty |
| `VolArbPnLTerm` | [vol_arb_pnl.py](../../aqp_rl/src/aqp_rl/rewards/vol_arb_pnl.py) | Lucic-Tse vol-arb reader |

### Rewards — MISSING (Phase 1 targets)

| Capability | Status | Action |
| --- | --- | --- |
| **Differential Sharpe Ratio (DSR)** — Moody & Saffell 1998 step-wise recurrence with `A_t, B_t` EMAs + `K_η` correction | MISSING (existing `SharpeTerm` is rolling, not differential) | ADD `aqp_rl/rewards/differential_sharpe.py::DifferentialSharpe` |
| **Differential Downside Deviation Ratio (D3R)** | MISSING | ADD `aqp_rl/rewards/differential_downside.py::DifferentialDownside` |
| **Implementation Shortfall reward** — `−(IS_step + λ·Var_step)/Q` | MISSING | ADD `aqp_rl/rewards/implementation_shortfall.py::ImplementationShortfall` |
| **Running Inventory Penalty (Cartea-Jaimungal full)** — `ΔPnL − φ·I²·Δt − α·I_T²·1{t=T}` (terminal term) | PARTIAL (`InventoryQuadraticPenaltyTerm` has only the running `-φ*q²`; terminal `α·I_T²` missing) | ADD `aqp_rl/rewards/inventory.py::RunningInventoryPenalty` with terminal flag |
| **Exponential Utility reward** — `−exp(−γ·PnL)` | MISSING | ADD `aqp_rl/rewards/exponential_utility.py::ExponentialUtility` |
| **Hindsight reward** (DeepScalper) — `compound · ((p_t+1 - p_t) + λ·(p_t+k - p_t))` | MISSING | ADD `aqp_rl/rewards/hindsight.py::HindsightReward` |
| **DP-distillation reward** — `MSE + ada·KL(softmax(Q), DP_demo)` | MISSING | ADD `aqp_rl/rewards/dp_distillation.py::DPDistillation` (composable surface; full HFT loss lives in the agent) |

## 3. Action / Observation / Termination — what exists

- **Actions** ([src/aqp_rl/core/action.py](../../aqp_rl/src/aqp_rl/core/action.py)): `ContinuousWeightsAction`, `SoftmaxWeightsAction`, `IntegerSharesAction`, `DiscreteBuySellHoldAction`, `MultiDiscreteAction`, `TargetPositionAction`. **MISSING**: maskable action wrapper (HFT pattern: `+ (avail - 1) · max_punish`) — folded into Phase 5 `HFTQBackbone` instead of an action subclass.
- **Observations** ([src/aqp_rl/observations/](../../aqp_rl/src/aqp_rl/observations/)): `covariance`, `fundamental`, `lookback`, `microstructure`, `portfolio_state`, `technical`, `turbulence`, `vix` + `StackedObservationBuilder`. **MISSING**: `RegimeAwareObservation` (Phase 6), `MultimodalDictObservation` (Phase 10).
- **Terminations** ([src/aqp_rl/terminations/](../../aqp_rl/src/aqp_rl/terminations/)): `drawdown`, `horizon`, `margin_call`, `risk_breach`, `turbulence`.

## 4. Advantage estimators — PRESENT

- `BaseAdvantageEstimator` + `AdvantageOutput` at [src/aqp_rl/advantage/base.py](../../aqp_rl/src/aqp_rl/advantage/base.py) (rule 36).
- Concrete: `GAEAdvantage` (Schulman 2016), `GRPOAdvantage` (group-relative), `ReinforcePlusPlusAdvantage` (NeMo-RL port).

## 5. Policy backbones — PRESENT

- `TimeSeriesEncoder` ABC at [src/aqp_rl/policies/backbones/base.py](../../aqp_rl/src/aqp_rl/policies/backbones/base.py) (rule 37).
- Concrete: `TransformerBackbone`, `RecurrentBackbone`, `AutoencoderBackbone`, `PatchTSTBackbone`.
- `BackboneFeaturesExtractor` SB3 bridge at [src/aqp_rl/policies/feature_extractors.py](../../aqp_rl/src/aqp_rl/policies/feature_extractors.py).

### Backbones — MISSING (Phase 5 targets)

| TradeMaster Source | New aqp_rl backbone alias | Action |
| --- | --- | --- |
| `trademaster/nets/eiie.py::EIIEConv` | `eiie_conv` | ADD |
| `trademaster/nets/ASU.py::SAGCN` (graph conv + TCN + spatial attention) | `sagcn` | ADD |
| `trademaster/nets/MSU.py::MSU` (LSTM + attention → (μ, σ)) | `market_scorer` | ADD |
| `trademaster/nets/high_frequency_trading_dqn.py::HFTQNet` (MLP + prev-action embed + action mask) | `hft_qnet` | ADD |
| `trademaster/nets/eteo.py::ETEOStacked` (MLP + dual heads) | `eteo_dual_head` | ADD |
| `trademaster/nets/pd.py::PDNet` (dual RNN public+private + (μ, σ, V)) | `pd_dual_rnn` | ADD |
| `trademaster/nets/sarl.py::LSTMClf` (LSTM classifier auxiliary task) | `sarl_lstm` | ADD |

## 6. Agents — PRESENT (current zoo)

[src/aqp_rl/agents/](../../aqp_rl/src/aqp_rl/agents/):

- **Adapters**: `sb3_adapter`, `elegantrl_adapter`, `rllib_adapter`, `cleanrl_adapter`, `nemo_rl_adapter`, `llm_hybrid`, `ensemble`
- **actor_critic family**: `actor_critic`, `actor_critic_duel`, `actor_critic_recurrent`
- **classical family**: `abcd`, `base`, `moving_average`, `signal_rolling`, `turtle`
- **evolutionary family**: `es`, `neuro`, `novelty`
- **q_family**: `q_learning`, `double_q`, `duel_q`, `recurrent_q`, `curiosity_q`
- **spm**: `spm/agents.py` (a3c / dqn / double_dueling_dqn / pg / evol)

### Agents — MISSING (Phase 4 targets)

| TradeMaster paper-grade source | New aqp_rl agent alias | Action |
| --- | --- | --- |
| `trademaster/agents/portfolio_management/eiie.py` | `eiie` | ADD (DDPG-style, EIIEConv actor + LSTM critic) |
| `trademaster/agents/portfolio_management/deeptrader.py` | `deeptrader` | ADD (ASU graph-NN actor + MSU market scorer + long-short `generate_portfolio`) |
| `trademaster/agents/portfolio_management/investor_imitator.py` | `investor_imitator` | ADD (REINFORCE with Categorical action) |
| `trademaster/agents/order_execution/eteo.py` | `eteo` | ADD (PPO with dual-head Normal volume+price) |
| `trademaster/agents/order_execution/pd.py` | `opd` (teacher-student dual PPO with KL distillation) | ADD |
| `trademaster/agents/algorithmic_trading/dqn.py` (DeepScalper) | `deepscalper` | ADD (DQN with hindsight reward) |
| `trademaster/agents/high_frequency_trading/ddqn.py` | `hft_ddqn` | ADD (DDQN with action masking + DP distillation) |
| In-house native PPO with full 37-trick checklist | `ppo_inhouse` | ADD (SB3 adapter exists but we want the canonical native impl for reproducibility) |
| `td3_inhouse`, `sac_inhouse`, `rainbow_inhouse` | | ADD (SB3 wraps them today but a native single-file class belongs in aqp_rl) |

## 7. Envs — PRESENT

[src/aqp_rl/envs/](../../aqp_rl/src/aqp_rl/envs/):

`portfolio_env`, `stock_trading_env`, `stock_trading_discrete`, `finrl_stock_env`, `finrl_portfolio_cov_env`, `finrl_crypto_env`, `finrl_stock_np_env`, `execution_env`, `optimal_execution_env`, `options_env`, `lucic_tse_options_env`, `mbtgym_adapter`, `market_making_env` (graduated AvSt), `rl_backtest_env` (bridge).

### Envs — MISSING (Phase 3 targets)

| TradeMaster source | New aqp_rl env alias | Action |
| --- | --- | --- |
| `trademaster/environments/portfolio_management/{environment,eiie_environment,sarl_environment,inverstor_imitator_environment,deeptrader_environment}.py` | `tradesim_portfolio` (EIIE-style `(F, N, T)` tensor + soft commission via weights-drift recalc + log-return reward) | ADD |
| `trademaster/environments/order_execution/{pd_environment,eteo_environment}.py` | `tradesim_execution` (private state `[t_left, q_left]` + perfect+imperfect dual state for OPD + IS reward + terminal liquidation) | ADD |
| `trademaster/environments/algorithmic_trading/environment.py` | `tradesim_algotrading` (discrete volume action with `[cash, position]` appended + hindsight forward window) | ADD |
| `trademaster/environments/high_frequency_trading/environment.py` | `tradesim_hft` (LOB-stacked state across 5 bid/ask levels + action masking via `+ (avail - 1) · max_punish` + DP demo in `info["DP_action"]` + `sell_value` / `buy_value` walking through depth) | ADD |
| `finagent/environment/trading.py` | `finagent_trading` (multimodal dict state `{price, news, guidance, sentiment, economic}`) | ADD (Phase 10) |

All Phase-3 envs **MUST** read via [aqp/data/datasets/](../../aqp/data/datasets/) `BaseDataset` (rule 29) — no `pd.read_csv` inside `__init__`.

## 8. Analytical baselines

| Location | What's there | Phase 2 verdict |
| --- | --- | --- |
| [aqp/optimal_control/avellaneda_stoikov.py](../../aqp/optimal_control/avellaneda_stoikov.py) | JAX-compiled `compute_optimal_quotes`, `AvellanedaStoikovParams`, `glft_closed_form` | PRESENT — Phase 2 ships a thin re-export under `aqp_rl/analytical/avellaneda_stoikov.py`. |
| [aqp/optimal_control/cartea_jaimungal.py](../../aqp/optimal_control/cartea_jaimungal.py) | HJB solver, `CarteaJaimungalParams`, `optimal_trading_rate`, `optimal_liquidation_value` | PRESENT — Phase 2 ships a thin re-export under `aqp_rl/analytical/cartea_jaimungal.py`. |
| Almgren-Chriss 2001 closed-form (`sinh`-schedule + `cost_expectation` + `cost_variance` + `kappa`) | MISSING (CJ ≠ AC — AC has cleaner closed forms for a deterministic schedule) | ADD `aqp_rl/analytical/almgren_chriss.py` matching paper equations 18, 20, 21 with `λ=10⁻⁶` default. |
| `AlmgrenChrissResidualPolicy` agent | MISSING | ADD Phase 2 alongside the math module. |
| `AvellanedaStoikovResidualPolicy` agent | MISSING (existing `MarketMakingEnv` does residual at env level, not as a separate agent) | ADD. |

## 9. Trajectory store / data pipelines / ensemblers / experiments / applications — PRESENT

- **Trajectory**: `IcebergTrajectoryStore` + `InMemoryTrajectoryStore` + DuckDB views at [src/aqp_rl/trajectories/](../../aqp_rl/src/aqp_rl/trajectories/).
- **Data pipelines**: `alpaca`, `iceberg`, `medallion_replay`, `replay`, `streaming`, `yahoo` at [src/aqp_rl/data_pipelines/](../../aqp_rl/src/aqp_rl/data_pipelines/).
- **Ensemblers**: `best_of_n`, `curriculum`, `meta_ensemble`, `walk_forward` at [src/aqp_rl/ensemblers/](../../aqp_rl/src/aqp_rl/ensemblers/).
- **Experiments**: `ablation`, `alpha_backtest`, `basic`, `walk_forward` at [src/aqp_rl/experiments/](../../aqp_rl/src/aqp_rl/experiments/).
- **Applications**: `cryptocurrency_trading`, `ensemble_strategy`, `fundamental_portfolio_drl`, `imitation_learning`, `papertrading_finrl`, `portfolio_allocation`, `stock_trading` at [src/aqp_rl/applications/](../../aqp_rl/src/aqp_rl/applications/).

## 10. Validation diagnostics — MISSING (Phase 8 targets)

| Capability | Phase 8 location |
| --- | --- |
| `CombinatorialPurgedKFold` (López de Prado AFML Ch.12; `φ(N,k) = C(N,k)·k/N` paths) | `aqp_rl/validation/cpcv.py` |
| `probability_of_backtest_overfitting` via CSCV (Bailey/Borwein/LDP/Zhu 2015) | `aqp_rl/validation/pbo.py` |
| `rademacher_anti_serum` (Paleologo 2024 §8.3, **EXPERIMENTAL**) | `aqp_rl/validation/rademacher.py` |
| `deflated_sharpe_ratio` (Bailey & LDP 2014) | `aqp_rl/validation/deflated_sharpe.py` |
| `walk_forward_anchored` + `walk_forward_rolling` | `aqp_rl/validation/walkforward.py` |
| `benjamini_hochberg` (FDR) + `holm_bonferroni` (FWER) | `aqp_rl/validation/multiple_testing.py` |
| `ValidationExperiment` kind | `aqp_rl/experiments/validation_suite.py` |

## 11. PRUDEX-Compass — MISSING (Phase 9 target)

[aqp_rl/src/aqp_rl/evaluation/](../../aqp_rl/src/aqp_rl/evaluation/) does NOT exist.
Phase 9 creates the directory and ships 17 measures + 5 visualizations (PRIDE-Star, Compass, Performance Profile, Rank Distribution, Extreme-Market) + `PrudexEvaluation` experiment kind.

## 12. Market Dynamics Modeling — MISSING (Phase 6 target)

| Capability | Phase 6 location |
| --- | --- |
| `SliceAndMergeRegimeFlow` analysis flow (port of `trademaster/utils/labeling_util.py::Worker`) | [aqp/analysis/flows/market_dynamics_modeling.py](../../aqp/analysis/flows/market_dynamics_modeling.py) (lives in the monolith per rule 23/24/25) |
| `RegimeAwareObservation` builder | `aqp_rl/observations/regime.py` |
| `task='test_dynamic'` mode on Phase 3 envs | inherited from env base |
| `RegimeStratifiedEvaluation` experiment | `aqp_rl/experiments/regime_stratified.py` |

## 13. CSDI diffusion imputation — MISSING (Phase 7 target)

Phase 7 creates `aqp/data/datasets/kinds/csdi_imputed.py` `BaseDataset` subclass per rule 29. Persists through `iceberg_catalog.append_arrow` (rule 3) — replaces TradeMaster's pickle pattern.

## 14. FinAgent — MISSING (Phase 10 target)

- `configs/agents/finagent/*.yaml` — 5 sub-spec AgentSpec YAMLs
- `aqp/agents/tools/finagent/{kline_plotter,trading_plotter,strategy_agents_tool}.py` — new tools
- `aqp_rl/agents/llm_hybrid_layered.py::LayeredReflectionAdapter` — wraps `LLMHybridAgent` with FinAgent's 5-layer prompt cascade via `AgentRuntime` (rule 12) + AQP's existing `RedisHybridMemory` (no FAISS dep)
- `MultimodalTradingEnv` from Phase 3

## 15. Replay buffer enhancements — MISSING (Phase 11 target)

[src/aqp_rl/core/replay.py](../../aqp_rl/src/aqp_rl/core/replay.py) only ships `InMemoryReplayBuffer` (deque FIFO). Phase 11 adds:

| Buffer | Source pattern |
| --- | --- |
| `GeneralReplayBuffer` (namedtuple-driven, generic shapes dict, deviceful tensors) | `trademaster/utils/general_replay_buffer.py` |
| `PrioritizedReplayBuffer` (sum-tree, α=0.6, β=0.4→1.0 annealing) | `trademaster/utils/replay_buffer.py::BinarySearchTree` |
| `NStepInfoReplayBuffer` (n-step with info dict for action masking + DP demo) | `trademaster/utils/replay_buffer.py::ReplayBufferHFT` |

## 16. Live execution + parity — PARTIAL (Phase 12 finalisation)

- `WeightCentricPipeline` PRESENT (rule 38).
- `WeightToOrders` + `apply_target_weights` PRESENT.
- `aqp/risk/kill_switch.is_engaged()` PRESENT and wired into the translator.
- **Need to verify in Phase 12**: live broker adapter coverage (Alpaca data exists at [src/aqp_rl/data_pipelines/alpaca.py](../../aqp_rl/src/aqp_rl/data_pipelines/alpaca.py); broker exec layer assumed to live in the monolith).
- **Reconciliation test** = 0 NAV diff between backtest engine and paper-broker session — to add.

## 17. Tests — PRESENT (mirror points)

[aqp_rl/tests/](../../aqp_rl/tests/):

- `test_action_spaces.py`, `test_observation_builders.py`, `test_reward_terms.py`, `test_data_pipelines.py`, `test_core_abstractions.py`
- `test_runtime.py`, `test_iceberg_writes.py`, `test_routes_rl.py`
- `test_stop_properly_shaping.py`
- `tests/advantage/test_reinforce_plus_plus.py`
- `tests/envs/test_market_making_env_avst.py`
- `tests/policies/test_backbones.py`
- `tests/portfolio/test_weight_centric_pipeline.py`

Phase-1 through Phase-12 each adds a matching test module under `tests/{rewards,analytical,envs,agents,policies/backbones,validation,evaluation,execution}/`.

## 18. Configs — PRESENT (sparse but layered)

[aqp_rl/configs/](../../aqp_rl/configs/):

- Top-level YAMLs: `actor_critic`, `avellaneda_stoikov_mm`, `cartea_jaimungal_execution`, `classical`, `ensemble_rotator`, `evolution`, `lucic_tse_options`, `ppo_portfolio`, `q_family`, `sac_trading`
- Sub-dirs: `data_pipelines/`, `observations/`, `policies/`, `presets/`, `rewards/`, `spm/`

Phase 1–12 adds matching YAMLs per new component alias under existing dirs (no new top-level dirs needed — `configs/{rewards,observations,policies,data_pipelines,spm}/` already exist; add `configs/{validation,evaluation,envs,agents,analytical,experiments}/` as needed).

## 19. Risks confirmed from recon

1. **`SharpeTerm` is rolling, not differential.** Phase 1 must NOT collide with it — ship `DifferentialSharpe` as a sibling class with a different `rl_alias`.
2. **`InventoryQuadraticPenaltyTerm` covers only the running term**, not the Cartea-Jaimungal terminal `α·I_T²·1{t=T}`. Phase 1 `RunningInventoryPenalty` extends it (don't overwrite).
3. **`MarketMakingEnv` already does AvSt residual at the env level.** Phase 2's `AvellanedaStoikovResidualPolicy` must be an agent that emits the residual, not duplicate the env logic.
4. **AvSt + CJ math already exists.** Phase 2 `aqp_rl/analytical/` modules are thin re-exports — do not re-implement.
5. **CJ != AC.** Almgren-Chriss has the cleaner `sinh`-schedule closed form (Almgren & Chriss 2001 eqs 18/20/21). Phase 2 ships AC fresh; do not try to coerce CJ into AC.
6. **All envs MUST read via `BaseDataset`.** Direct `pd.read_csv` inside env `__init__` violates rule 29. TradeMaster's envs all do this — Phase 3 ports must rewrite the data path.
7. **`StopProperlyWrapper` already wraps `BaseRewardModel`.** New differential rewards must NOT break the truncation-scaling math when composed.

## 20. Phase-0 acceptance — MET

✅ Every existing `rl_kind` is enumerated with file paths.
✅ Every blueprint + TradeMaster capability flagged PRESENT / PARTIAL / MISSING with concrete file targets.
✅ Hard rules 16-20 + 36-39 + 45 confirmed as the invariants every Phase 1-12 deliverable must respect.

Proceeding to Phase 1.
