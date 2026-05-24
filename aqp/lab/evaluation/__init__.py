"""Evaluation-mode primitives: CPCV, Deflated Sharpe, sweep controllers.

Per the plan's Phase 3:

- :mod:`aqp.lab.evaluation.cpcv` — Combinatorial Purged CV (López de
  Prado, *Advances in Financial Machine Learning*, ch.7) with a hard
  guard on path-count explosion.
- :mod:`aqp.lab.evaluation.deflated_sharpe` — Deflated Sharpe Ratio
  (DSR) so the UI never displays raw Sharpe alone.
- :mod:`aqp.lab.evaluation.sweep` — pluggable sweep controllers
  (grid / random / Optuna TPE / Ray Tune ASHA) — the optuna / ray
  backends are soft deps that degrade to grid+random when missing.
"""
from __future__ import annotations

from aqp.lab.evaluation.cpcv import (
    CPCVConfig,
    CPCVPath,
    CPCVPlanError,
    combinatorial_purged_cv,
    safe_cpcv_path_count,
)
from aqp.lab.evaluation.deflated_sharpe import (
    deflated_sharpe_ratio,
    probabilistic_sharpe_ratio,
)
from aqp.lab.evaluation.sweep import (
    SweepController,
    SweepTrial,
    grid_sweep,
    optuna_tpe_sweep,
    random_sweep,
)

__all__ = [
    "CPCVConfig",
    "CPCVPath",
    "CPCVPlanError",
    "SweepController",
    "SweepTrial",
    "combinatorial_purged_cv",
    "deflated_sharpe_ratio",
    "grid_sweep",
    "optuna_tpe_sweep",
    "probabilistic_sharpe_ratio",
    "random_sweep",
    "safe_cpcv_path_count",
]
