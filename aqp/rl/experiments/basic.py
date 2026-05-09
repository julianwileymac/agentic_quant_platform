"""``BasicRLExperiment`` — single train + holdout eval.

Mirrors :func:`aqp.rl.trainer.train_from_config` but goes through
:class:`aqp.rl.runtime.RLRuntime` so trajectory persistence and run
ledger writes happen for free.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from aqp.rl.core.experiment import BaseExperiment

logger = logging.getLogger(__name__)


class BasicRLExperiment(BaseExperiment):
    """Train + evaluate a single spec end-to-end."""

    rl_alias: ClassVar[str] = "BasicRLExperiment"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "single-pass"
    rl_tags: ClassVar[tuple[str, ...]] = ("baseline",)

    def run(self, spec: Any, runtime: Any) -> dict[str, Any]:
        train_outcome = runtime._do_train(run_name=spec.slug, overrides={})  # noqa: SLF001
        ckpt = train_outcome.get("checkpoint")
        if ckpt is None:
            return {"train": train_outcome, "evaluate": None}
        try:
            eval_outcome = runtime._do_evaluate(checkpoint=ckpt, overrides={})  # noqa: SLF001
        except Exception:  # noqa: BLE001
            logger.exception("BasicRLExperiment evaluate stage failed")
            eval_outcome = None
        return {"train": train_outcome, "evaluate": eval_outcome}


__all__ = ["BasicRLExperiment"]
