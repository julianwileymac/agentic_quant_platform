---
title: 'RL PRUDEX-Compass Evaluation (Phase 9)'
summary: '| Axis | Code | Measures | | --- | --- | --- | | Profitability | P | `total_return`, `annualised_return`, `cagr` | | Risk-control | R | `volatility`, `max_drawdown`, `sortino`, `calmar` | | Universali...'
owner: rl-team
last_reviewed: 2026-05-25
audience: both
---

# RL PRUDEX-Compass Evaluation (Phase 9)

Reference docs for the PRUDEX-Compass evaluation framework ported
from TradeMaster into `aqp_rl`.

## Six axes, 17 measures

| Axis | Code | Measures |
| --- | --- | --- |
| Profitability | P | `total_return`, `annualised_return`, `cagr` |
| Risk-control | R | `volatility`, `max_drawdown`, `sortino`, `calmar` |
| Universality | U | `cross_dataset_sharpe_mean`, `cross_dataset_sharpe_std` |
| Diversification | D | `portfolio_weight_entropy`, `turnover` |
| Explainability | E | `regime_conditioned_sharpe` |
| X-tra evaluation | X | `performance_profile_auc`, `rank_score`, `extreme_market_score`, `hit_rate` |

Plus a `sharpe_ratio` convenience field. **17 measures total.**

## Five visualisations

| Helper | Purpose |
| --- | --- |
| `pride_star_chart` | 8-axis radar of per-agent scores |
| `prudex_compass_chart` | 6-axis octagon (one axis per PRUDEX axis) |
| `performance_profile_chart` | CDF of per-step returns across agents |
| `rank_distribution_chart` | Heatmap of per-metric ranks |
| `extreme_market_chart` | Bar chart of extreme-market cumulative returns |

All helpers gracefully degrade to a dict fallback when matplotlib
is unavailable.

## Modules

| File | Class | Purpose |
| --- | --- | --- |
| [`aqp_rl/src/aqp_rl/evaluation/prudex_compass.py`](../aqp_rl/src/aqp_rl/evaluation/prudex_compass.py) | `PrudexMetrics`, `PrudexReport`, `compute_prudex_metrics` | Per-agent metric computation |
| [`aqp_rl/src/aqp_rl/evaluation/visualizations.py`](../aqp_rl/src/aqp_rl/evaluation/visualizations.py) | 5 chart helpers | Plot rendering |
| [`aqp_rl/src/aqp_rl/experiments/prudex_evaluation.py`](../aqp_rl/src/aqp_rl/experiments/prudex_evaluation.py) | `PrudexEvaluation` | Experiment aggregator |

## Usage

```python
from aqp_rl.experiments.prudex_evaluation import PrudexEvaluation
from aqp_rl.evaluation.visualizations import (
    prudex_compass_chart, pride_star_chart, performance_profile_chart,
)

exp = PrudexEvaluation(periods_per_year=252)
report = exp.run(
    agent_results={
        "eiie": {"equity_curve": eq_eiie, "weights_history": w_eiie},
        "deeptrader": {"equity_curve": eq_dt, "weights_history": w_dt},
        "ppo": {"equity_curve": eq_ppo, "weights_history": w_ppo},
    },
)
# Visualise:
fig = prudex_compass_chart(report)
```

## Hard rule alignment

- Hard rule 19: `PrudexEvaluation` registers via
  `RLComponent` metaclass under `rl_alias='prudex_compass'`.
- Hard rule 18: report lands in `rl_runs.result_summary` via the
  parent `RLRuntime`; no direct Iceberg writes from this experiment.

## Acceptance

[Phase 9 tests](../aqp_rl/tests/evaluation/) verify:

- All 17 measures compute without error on synthetic equity series.
- Per-axis breakdown has exactly 6 axes (P/R/U/D/E/X).
- 5 visualisation helpers return a Figure (matplotlib) or dict
  fallback.
- Rank matrix is in `[1, N_agents]` per metric.
