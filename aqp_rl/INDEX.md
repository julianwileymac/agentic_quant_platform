# aqp_rl Index

## Live Implementation

- Spec + runtime: `src/aqp_rl/spec.py`, `src/aqp_rl/runtime.py`,
  `src/aqp_rl/registry.py`.
- Core ABCs + metaclass: `src/aqp_rl/core/base.py`,
  `src/aqp_rl/core/{env,observation,action,reward,termination,policy,data,ensembler,experiment,replay,schemas}.py`.
- Component libraries: `src/aqp_rl/{envs,rewards,observations,actions,terminations,policies,data_pipelines,agents,ensemblers,experiments,applications,portfolio,bridges,advantage,trajectories,execution}/`.
- Celery task: `tasks/rl_tasks.py`.
- FastAPI route: `api/routes/rl.py`.
- Persistence models (in monolith): `../aqp/persistence/models_rl.py`.
- Spec library: `configs/`.
- Canonical docs: `../aqp_docs/docs/concepts/rl/rl-framework.md`,
  `../aqp_docs/docs/concepts/rl/rl-lab.md`, `../aqp_docs/docs/concepts/rl/rl-components.md`,
  `../aqp_docs/docs/concepts/rl/rl-iceberg.md`, `../aqp_docs/docs/concepts/rl/rl-policy-backbones.md`,
  `../aqp_docs/docs/concepts/rl/weight-centric-pipeline.md`.

## Core abstraction families

| Family | Base class | rl_kind | Examples |
| --- | --- | --- | --- |
| Environment | `BaseRLEnv` | `rl_env` | `PortfolioAllocationEnv`, `StockTradingEnv`, `MarketMakingEnv`, `OptimalExecutionEnv`, `LucicTseOptionsEnv`, `RLBacktestEnv`, FinRL ports |
| Observation | `BaseObservationBuilder` | `rl_observation` | technical, covariance, lookback, microstructure, fundamental, turbulence, VIX, portfolio_state |
| Action | `BaseActionSpace` | `rl_action` | continuous, softmax, integer-shares, discrete, multi-discrete, target-position |
| Reward | `RewardTerm` | `rl_reward` | pnl, risk, cost, gating, shaping, constraint, inventory_quadratic, vol_arb_pnl, stop_properly |
| Termination | `BaseTermination` | `rl_termination` | drawdown, horizon, risk_breach, turbulence, margin_call |
| Policy | `BasePolicy` | `rl_policy` | SB3 / ElegantRL / RLlib / CleanRL / classical / Q-family / actor-critic / evolutionary / SPM |
| Agent | `BaseRLAgent` | `rl_agent` | (per framework adapter) |
| Data pipeline | `BaseDataPipeline` | `rl_data` | iceberg, yahoo, alpaca, replay, streaming, medallion_replay |
| Ensembler | `BaseEnsembler` | `rl_ensembler` | walk_forward, meta_ensemble, best_of_n, curriculum |
| Experiment | `BaseExperiment` | `rl_experiment` | basic, ablation, alpha_backtest |
| Trajectory store | `BaseTrajectoryStore` | `rl_trajectory_store` | `IcebergTrajectoryStore` |
| Advantage estimator | `BaseAdvantageEstimator` | `rl_advantage_estimator` | REINFORCE++, GRPO, GAE |
| Policy backbone | `TimeSeriesEncoder` | `rl_policy_backbone` | Transformer, Recurrent, Autoencoder, PatchTST |

## Future Extraction Gates

1. Define a stable HTTP / gRPC contract for `RLRuntime` lifecycle so the
   monolith API gateway can call into a separate process.
2. Carve out persistence models (`rl_runs`, `rl_experiment_versions`,
   `rl_trajectory_*`) into a shared schema so this boundary can run with
   its own ORM session.
3. Replace the direct dependency on `iceberg_catalog.append_arrow` with a
   thin client that respects the same medallion + business-metadata
   contract.
4. Replace the direct dependency on `router_complete` with an HTTP
   endpoint exposed by the LLM gateway.

When all four are met, `aqp_rl` is ready to extract into its own
repository per the Future Repo Split Gate in
[`../aqp_docs/docs/concepts/platform/repository-split.md`](../aqp_docs/docs/concepts/platform/repository-split.md).
