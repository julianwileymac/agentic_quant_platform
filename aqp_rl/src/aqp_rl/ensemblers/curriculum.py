"""``CurriculumRunner`` — sequential training over progressively harder windows."""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from aqp_rl.core.ensembler import BaseEnsembler

logger = logging.getLogger(__name__)


class CurriculumRunner(BaseEnsembler):
    """Train one agent in sequence over a list of (start, end) windows."""

    rl_alias: ClassVar[str] = "CurriculumRunner"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "curriculum"
    rl_tags: ClassVar[tuple[str, ...]] = ("curriculum", "progressive")

    def __init__(self, *, windows: list[dict[str, str]]) -> None:
        super().__init__()
        self.windows = list(windows or [])

    def train(self, spec: Any, runtime: Any) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for idx, w in enumerate(self.windows):
            overrides = {"env": {"kwargs": {"start": w.get("start"), "end": w.get("end")}}}
            try:
                outcome = runtime._do_train(run_name=f"{spec.slug}-w{idx}", overrides=overrides)  # noqa: SLF001
                results.append({"window": w, "outcome": outcome})
            except Exception:  # noqa: BLE001
                logger.exception("curriculum window %d failed", idx)
        return {"windows": results}


__all__ = ["CurriculumRunner"]
