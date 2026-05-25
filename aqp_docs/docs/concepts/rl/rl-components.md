---
title: 'RL component reference'
summary: '| `rl_kind` | Purpose | Base class | | --- | --- | --- | | `rl_env` | Gymnasium env | [`BaseRLEnv`](../aqp/rl/core/env.py) | | `rl_observation` | State featuriser | [`BaseObservationBuilder`](../aqp/r...'
owner: rl-team
last_reviewed: 2026-05-25
audience: both
---

# RL component reference

> This page is a hand-written shortcut. The authoritative source is the
> live registry exposed by `GET /rl/components/{kind}` (and rendered in
> the UI at [`/rl/library`](../webui/app/(shell)/rl/library/page.tsx)).

## Kinds

| `rl_kind` | Purpose | Base class |
| --- | --- | --- |
| `rl_env` | Gymnasium env | [`BaseRLEnv`](../aqp/rl/core/env.py) |
| `rl_observation` | State featuriser | [`BaseObservationBuilder`](../aqp/rl/core/observation.py) |
| `rl_action` | Action-space spec + transform | [`BaseActionSpace`](../aqp/rl/core/action.py) |
| `rl_reward` | Reward term / composite | [`BaseRewardModel`](../aqp/rl/core/reward.py), [`RewardTerm`](../aqp/rl/core/reward.py) |
| `rl_termination` | End-of-episode predicate | [`BaseTerminationCondition`](../aqp/rl/core/termination.py) |
| `rl_policy` | Frozen policy | [`BasePolicy`](../aqp/rl/core/policy.py) |
| `rl_agent` | Train-aware agent | [`BaseRLAgent`](../aqp/rl/core/policy.py) |
| `rl_data` | Data pipeline | [`BaseDataPipeline`](../aqp/rl/core/data.py) |
| `rl_ensembler` | Multi-member orchestrator | [`BaseEnsembler`](../aqp/rl/core/ensembler.py) |
| `rl_experiment` | Experiment runner | [`BaseExperiment`](../aqp/rl/core/experiment.py) |
| `rl_trajectory_store` | Per-step persistence | [`BaseTrajectoryStore`](../aqp/rl/core/replay.py) |

## Built-in components (FinRL + AQP)

### Environments
- `StockTradingEnv` — continuous portfolio (existing).
- `PortfolioAllocationEnv` — softmax weights (existing).
- `StockTradingDiscreteEnv` — single-stock buy/sell/hold (existing).
- `FinRLStockTradingEnv` — pandas share-lots (FinRL port).
- `FinRLStockTradingNpEnv` — array-backed numpy (FinRL port).
- `FinRLPortfolioCovEnv` — covariance + softmax (FinRL port).
- `FinRLCryptoEnv` — multi-crypto lookback stack (FinRL port).
- `OptionsTradingEnv`, `ExecutionEnv`, `MarketMakingEnv` — placeholders.

### Reward terms
- `PnLTerm`, `LogReturnTerm`
- `SharpeTerm`, `SortinoTerm`, `DrawdownPenaltyTerm`, `VolatilityPenaltyTerm`
- `TurnoverPenaltyTerm`, `TransactionCostTerm`, `SlippagePenaltyTerm`
- `TurbulenceGateTerm`, `MarginCallTerm`
- `CashIdlePenaltyTerm`, `BenchmarkOutperformanceTerm`, `RiskParityTerm`
- `PotentialBasedShaping`
- `CompositeReward` (sum of weighted terms; emits per-term
  contributions to `info["reward_terms"]`).

### Observation builders
- `PortfolioStateBuilder` (cash + weights / positions)
- `TechnicalIndicatorBuilder` (FinRL stockstats)
- `CovarianceBuilder` (FinRL portfolio cov)
- `TurbulenceBuilder` (Mahalanobis stress)
- `VIXBuilder`
- `LookbackStackBuilder` (FinRL crypto)
- `FundamentalBuilder` (FinRobot bridge)
- `MicrostructureBuilder`
- `StackedObservationBuilder` (composite)

### Action spaces
- `ContinuousWeightsAction`, `SoftmaxWeightsAction`,
  `IntegerSharesAction`, `DiscreteBuySellHoldAction`,
  `MultiDiscreteAction`, `TargetPositionAction`.

### Termination conditions
- `HorizonTermination`, `DrawdownTermination`, `MarginCallTermination`,
  `TurbulenceTermination`.

### Data pipelines
- `IcebergRLDataPipeline` (default — AQP catalog).
- `YahooFinanceRLDataPipeline` (FinRL parity).
- `AlpacaRLDataPipeline` (paper-trading bridge).
- `LiveStreamingRLDataPipeline` (Kafka / Flink).
- `ReplayRLDataPipeline` (offline RL from `rl.trajectories`).

### Agents
- `SB3Adapter` — PPO / A2C / DDPG / SAC / TD3 / DQN +
  sb3-contrib (RecurrentPPO / TRPO / QRDQN / MaskablePPO / ARS / TQC).
- `ElegantRLAdapter`, `RayRLlibAdapter`, `CleanRLAdapter`.
- `LLMHybridAgent` — FinRobot-style LLM advisor + RL backbone.
- Existing classical / Q-family / actor-critic / evolutionary / SPM
  trees retained.

### Ensemblers / experiments
- `WalkForwardEnsembler` (FinRL `DRLEnsembleAgent` port).
- `BestOfNRunner`, `CurriculumRunner`, `MetaEnsembleRunner`.
- `BasicRLExperiment`, `WalkForwardRLExperiment`,
  `RewardAblationExperiment`, `RLAlphaBacktestExperiment`.
