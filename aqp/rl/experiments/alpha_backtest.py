"""``RLAlphaBacktestExperiment`` — bridge to AQP's combined ML+backtest unit.

Mirrors :class:`aqp.ml.alpha_backtest_experiment.AlphaBacktestExperiment`
for the RL world: train an RL policy, register a checkpoint as an
"alpha", run a backtest using the policy's predictions, and persist a
combined run record so the UI can compare RL alphas alongside ML alphas.

This module is intentionally thin — heavy logic lives in
:class:`AlphaBacktestExperiment` (which is supervised-ML focused). The
RL wrapper here trains via :class:`RLRuntime` and then calls the
backtest primitive on the resulting checkpoint, mapping policy actions
to portfolio weights through
:class:`aqp.strategies.rl_policy.RLPolicyAlpha` (already in the repo).
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from aqp.rl.core.experiment import BaseExperiment

logger = logging.getLogger(__name__)


class RLAlphaBacktestExperiment(BaseExperiment):
    """Train an RL policy → register checkpoint → run backtest as alpha."""

    rl_alias: ClassVar[str] = "RLAlphaBacktestExperiment"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "alpha-backtest"
    rl_tags: ClassVar[tuple[str, ...]] = ("rl-as-alpha", "backtest")

    def run(self, spec: Any, runtime: Any) -> dict[str, Any]:
        train_outcome = runtime._do_train(run_name=spec.slug, overrides={})  # noqa: SLF001
        ckpt = train_outcome.get("checkpoint")
        if ckpt is None:
            return {"train": train_outcome, "backtest": None}
        try:
            from aqp.backtest.runner import run_backtest_from_config

            cfg = self._derive_backtest_cfg(spec, ckpt)
            backtest = run_backtest_from_config(cfg)
        except Exception:  # noqa: BLE001
            logger.exception("RLAlphaBacktestExperiment backtest stage failed")
            backtest = None
        return {"train": train_outcome, "backtest": backtest}

    def _derive_backtest_cfg(self, spec: Any, checkpoint: str) -> dict[str, Any]:
        symbols = list(spec.universe.symbols or [])
        return {
            "engine": "event-driven",
            "strategy": {
                "class": "FrameworkAlgorithm",
                "module_path": "aqp.strategies.framework",
                "kwargs": {
                    "universe_model": {"class": "StaticUniverse", "kwargs": {"symbols": symbols}},
                    "alpha_model": {
                        "class": "RLPolicyAlpha",
                        "module_path": "aqp.strategies.rl_policy",
                        "kwargs": {
                            "checkpoint_path": str(checkpoint),
                            "agent_spec": spec.agent or {},
                        },
                    },
                    "portfolio_model": {"class": "EqualWeightPortfolio"},
                    "risk_model": {"class": "NoOpRiskModel"},
                    "execution_model": {"class": "ImmediateExecutionModel"},
                },
            },
            "data": {
                "symbols": symbols,
                "start": spec.evaluation.start or (spec.env or {}).get("kwargs", {}).get("start"),
                "end": spec.evaluation.end or (spec.env or {}).get("kwargs", {}).get("end"),
            },
            "initial_cash": (spec.env or {}).get("kwargs", {}).get("initial_balance", 100_000.0),
        }


__all__ = ["RLAlphaBacktestExperiment"]
