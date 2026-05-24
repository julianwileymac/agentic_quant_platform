"""Validation diagnostics — CPCV, PBO, RAS, DSR, walk-forward, multiple testing.

This sub-package ships the canonical selection-bias-aware diagnostics
referenced in the production-enhancement plan's Phase 8:

- :class:`CombinatorialPurgedKFold` (López de Prado AFML Ch.12).
- :func:`probability_of_backtest_overfitting` via CSCV
  (Bailey/Borwein/López de Prado/Zhu 2015).
- :func:`rademacher_anti_serum` (Paleologo 2024 *Elements of
  Quantitative Investing* §8.3) — marked **EXPERIMENTAL**.
- :func:`deflated_sharpe_ratio` (Bailey & López de Prado 2014 closed
  form).
- :func:`walk_forward_anchored` + :func:`walk_forward_rolling`.
- :func:`benjamini_hochberg` (FDR) + :func:`holm_bonferroni` (FWER)
  multiple-testing corrections.

Plus :class:`ValidationExperiment` — the
:class:`aqp_rl.core.experiment.BaseExperiment` subclass that runs the
diagnostic suite over a trained agent's per-strategy returns.

Hard rule 19: every component registers via the
:class:`RLComponent` metaclass under ``rl_kind='rl_experiment'``
where applicable; the diagnostic helpers themselves are plain
functions called from inside the experiment.
"""
from __future__ import annotations

from aqp_rl.validation.cpcv import CombinatorialPurgedKFold, combinatorial_paths_count
from aqp_rl.validation.deflated_sharpe import deflated_sharpe_ratio
from aqp_rl.validation.multiple_testing import (
    benjamini_hochberg,
    holm_bonferroni,
)
from aqp_rl.validation.pbo import probability_of_backtest_overfitting
from aqp_rl.validation.rademacher import (
    empirical_rademacher_complexity,
    rademacher_anti_serum,
)
from aqp_rl.validation.walkforward import (
    walk_forward_anchored,
    walk_forward_rolling,
)

__all__ = [
    "CombinatorialPurgedKFold",
    "benjamini_hochberg",
    "combinatorial_paths_count",
    "deflated_sharpe_ratio",
    "empirical_rademacher_complexity",
    "holm_bonferroni",
    "probability_of_backtest_overfitting",
    "rademacher_anti_serum",
    "walk_forward_anchored",
    "walk_forward_rolling",
]
