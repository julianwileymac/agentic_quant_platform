"""``WalkForwardRLExperiment`` — chains multiple training windows."""
from __future__ import annotations

from typing import Any, ClassVar

from aqp_rl.core.experiment import BaseExperiment
from aqp_rl.ensemblers.walk_forward import WalkForwardEnsembler


class WalkForwardRLExperiment(BaseExperiment):
    """Walk-forward training experiment.

    Convenience wrapper that ensures the spec carries an ensembler block
    and dispatches to :class:`WalkForwardEnsembler.train`.
    """

    rl_alias: ClassVar[str] = "WalkForwardRLExperiment"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "walk-forward"
    rl_tags: ClassVar[tuple[str, ...]] = ("ensemble", "rolling")

    def run(self, spec: Any, runtime: Any) -> dict[str, Any]:
        ensembler = WalkForwardEnsembler(
            members=(spec.ensembler.members if spec.ensembler else []),
        )
        return ensembler.train(spec, runtime)


__all__ = ["WalkForwardRLExperiment"]
