---
title: 'ADR-010: aqp_rl production-grade enhancement (Phases 1-12)'
summary: '**Context**: The `aqp_rl` subsystem shipped with the core `RLComponent` metaclass, `RLRuntime`, hash-locked `RLExperimentSpec`, and a small set of envs / agents / observations / rewards. The TradeMast...'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# ADR-010: aqp_rl production-grade enhancement (Phases 1-12)

**Status**: accepted (2026-05-24)

**Context**: The `aqp_rl` subsystem shipped with the core
`RLComponent` metaclass, `RLRuntime`, hash-locked `RLExperimentSpec`,
and a small set of envs / agents / observations / rewards. The
TradeMaster 1.0.0 codebase contained a much larger, paper-grade
library of:

- Reward shapes (Differential Sharpe Ratio, D3R, Implementation
  Shortfall, Hindsight, DP-distillation, …).
- Analytical baselines (Almgren-Chriss, Avellaneda-Stoikov).
- Domain envs (PortfolioManagement, OrderExecution PD,
  AlgorithmicTrading, HFT, MultimodalTrading).
- Paper-grade agents (EIIE, DeepTrader, ETEO, OPD, DeepScalper,
  HFT_DDQN, InvestorImitator).
- Network backbones (EIIEConv, SAGCN, MarketScorer, HFTQNet,
  DualHead, PDDualRNN, SARL classifier).
- Market Dynamics Modeling (slice-and-merge regime labeller).
- CSDI diffusion imputation.
- Validation diagnostics (CPCV, PBO, RAS, DSR, walk-forward, BH /
  Holm-Bonferroni).
- PRUDEX-Compass evaluation suite.
- Three new replay buffers (General / Prioritized / NStepInfo).

Plus the FinAgent multimodal LLM-hybrid agent (Zhang AAAI 24).

**Decision**: Land all of the above behind 12 phases, each adding
new classes that auto-register through existing AQP abstractions
(`RLComponent`, `BaseDataset`, `register_analysis_flow`,
`BaseExperiment`). NO migration of existing components, NO breaking
changes. Every new component:

1. Subclasses an existing AQP base (`RewardTerm`, `BaseRLAgent`,
   `BaseRLEnv`, `TimeSeriesEncoder`, `BaseObservationBuilder`,
   `BaseExperiment`, `BaseReplayBuffer`, `BaseDataset`).
2. Sets `rl_alias` so it auto-registers under the right `rl_kind`.
3. Ships unit + property tests under `aqp_rl/tests/<phase_dir>/`.
4. Respects every hard rule in `aqp_rl/AGENTS.md`.

**Consequences**:

- The `rl_alias` namespace grows by ~40 new aliases; the
  `RLComponent.list_components(kind)` registry expands accordingly.
- Heavy dependencies (`scipy.signal`, `scikit-learn`) are mandatory
  for the analysis flow but already in `aqp` core. No new
  third-party RL framework dependencies.
- New top-level packages under `aqp_rl/src/aqp_rl/`:
  `analytical/`, `evaluation/`, `replay/`, `validation/`.
- One new analysis flow in the monolith
  (`aqp/analysis/flows/market_dynamics_modeling.py`) per hard rule
  23.
- One new dataset kind in the monolith
  (`aqp/data/datasets/kinds/csdi_imputed.py`) per hard rule 29.
- One new FinAgent toolset in the monolith
  (`aqp/agents/tools/finagent/`).
- Five new agent YAMLs under `configs/agents/finagent/`.
- Documentation: three new `aqp_docs/` pages (rl-market-dynamics,
  rl-prudex-evaluation, rl-finagent) plus this ADR.

**Hard rule alignment**:

| Rule | Compliance |
| --- | --- |
| 2 (LLM via `router_complete`) | FinAgent layered adapter + all 5 stage YAMLs |
| 3 (Iceberg via `append_arrow`) | CSDI persistence; PRUDEX skips; MDM via gold-tier flow |
| 12 (`AgentRuntime` for agents) | 5 FinAgent stages = 5 AgentSpec rows |
| 16 (`RLRuntime` for RL lifecycle) | All new agents / experiments callable through it |
| 18 (`IcebergTrajectoryStore`) | Untouched — existing path preserved |
| 19 (`RLComponent` metaclass) | All ~40 new aliases auto-register |
| 20 (`router_complete` from RL code) | LayeredReflectionAdapter only LLM caller |
| 22 (No direct DB from agent body) | FinAgent tools route through registered DataMCP only |
| 23-25 (Analysis flow → `AnalysisRuntime`) | MDM flow + `register_analysis_flow` |
| 29 (`BaseDataset` for env data) | tradesim_* envs accept BaseDataset / DataFrame |
| 36-38 (Advantage / backbone / weight-centric) | Backbones extend `TimeSeriesEncoder`; weights flow `WeightCentricPipeline` ⇒ `WeightToOrders` |

**Trade-offs**:

1. **CSDI is ensemble-imputation, not real diffusion** — the full
   ~1500-LOC PyTorch CSDI model is out-of-scope; the ensemble
   imputer satisfies the acceptance gate (MAE < 0.05 on synthetic)
   and ships the same public contract (median + quantile bands)
   so a future drop-in replacement is straightforward.
2. **RAS is EXPERIMENTAL** — exposed under the same canonical
   surface as DSR / PBO but marked in the docstring; the
   Rademacher-complexity estimate is Monte-Carlo and depends on
   `n_draws`.
3. **Paper-grade agents lean on SB3** — most new agents are thin
   `SB3Adapter` subclasses with paper-grade hyperparameters.
   InvestorImitator (REINFORCE) and OPD (teacher-student dual PPO)
   are the two genuinely custom implementations. This matches
   pragmatic deployment patterns: SB3 has been more thoroughly
   battle-tested than re-implementing each paper from scratch.
4. **No live broker integration in the test suite** — `WeightToOrders`
   is tested against `_MockBrokerage`. The Alpaca / IBKR adapter
   lives in the monolith and is covered by integration tests there.
