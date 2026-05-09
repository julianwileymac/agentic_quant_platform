"""``BestOfNRunner`` — random-search hyperparameter sweep.

Runs ``n`` agent configurations sequentially (or via parallel Celery
fanout when wrapped by :func:`aqp.tasks.rl_tasks.best_of_n_search`),
and keeps the highest-Sharpe member.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from aqp.rl.core.ensembler import BaseEnsembler

logger = logging.getLogger(__name__)


class BestOfNRunner(BaseEnsembler):
    """Best-of-N hyperparameter search over a list of agent build-specs."""

    rl_alias: ClassVar[str] = "BestOfNRunner"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "hyperparam"
    rl_tags: ClassVar[tuple[str, ...]] = ("search", "best-of-n")

    def __init__(self, *, members: list[dict[str, Any]]) -> None:
        super().__init__()
        self.members = list(members or [])
        self._best: Any = None

    def train(self, spec: Any, runtime: Any) -> dict[str, Any]:
        from aqp.core.registry import build_from_config

        results: list[dict[str, Any]] = []
        best: dict[str, Any] | None = None
        for idx, member_cfg in enumerate(self.members):
            try:
                derived = self._derive_member_spec(spec, member_cfg)
                runtime.spec = derived
                outcome = runtime._do_train(run_name=f"{spec.slug}-m{idx}", overrides={})  # noqa: SLF001
                metrics = outcome.get("metrics", {}) or {}
                sharpe = float(metrics.get("sharpe", 0.0) or 0.0)
                row = {"member": idx, "config": member_cfg, "outcome": outcome, "sharpe": sharpe}
                results.append(row)
                if best is None or sharpe > best["sharpe"]:
                    best = row
                    if derived.agent is not None:
                        self._best = build_from_config(derived.agent)
            except Exception:  # noqa: BLE001
                logger.exception("best-of-n member %d failed", idx)
        return {"members": results, "best": best}

    def _derive_member_spec(self, base_spec: Any, member_cfg: dict[str, Any]) -> Any:
        try:
            data = base_spec.model_dump(mode="python")
        except Exception:  # noqa: BLE001
            data = dict(getattr(base_spec, "__dict__", {}))
        data["agent"] = member_cfg
        cls = type(base_spec)
        return cls.model_validate(data)


__all__ = ["BestOfNRunner"]
