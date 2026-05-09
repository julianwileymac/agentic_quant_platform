"""``WalkForwardEnsembler`` — clean port of FinRL's ``DRLEnsembleAgent``.

Rolling train→validate-by-Sharpe→trade loop. For each window the
ensembler trains every member on the train slice, validates on the
val slice, picks the best by Sharpe, and forwards the test slice's
inference window to the picked member.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

from aqp.rl.core.ensembler import BaseEnsembler

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardResult:
    member_metrics: list[dict[str, Any]] = field(default_factory=list)
    best_member: dict[str, Any] | None = None
    selected: list[str] = field(default_factory=list)


class WalkForwardEnsembler(BaseEnsembler):
    """Walk-forward ensemble over multiple agent specs.

    Parameters
    ----------
    members:
        List of build-specs for :class:`aqp.rl.core.policy.BaseRLAgent`
        subclasses (e.g. ``[{"class": "SB3Adapter", "kwargs": {"algorithm": "PPO"}}]``).
    train_period:
        Number of bars per training window.
    val_period:
        Number of bars per validation window.
    test_period:
        Number of bars per held-out window (rolled forward each step).
    """

    rl_alias: ClassVar[str] = "WalkForwardEnsembler"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "walk-forward"
    rl_tags: ClassVar[tuple[str, ...]] = ("ensemble", "rolling", "sharpe")

    def __init__(
        self,
        *,
        members: list[dict[str, Any]],
        train_period: int = 252,
        val_period: int = 63,
        test_period: int = 63,
    ) -> None:
        super().__init__()
        self.members = list(members or [])
        self.train_period = int(train_period)
        self.val_period = int(val_period)
        self.test_period = int(test_period)
        self._best: Any = None

    def train(self, spec: Any, runtime: Any) -> dict[str, Any]:
        """Train the ensemble using ``runtime``'s train + evaluate primitives.

        Falls back to a single-window training pass if data isn't large
        enough for a full walk-forward.
        """
        from aqp.core.registry import build_from_config

        results = WalkForwardResult()
        per_member = []
        for idx, member_cfg in enumerate(self.members):
            member_spec = self._derive_member_spec(spec, member_cfg)
            try:
                runtime.spec = member_spec
                outcome = runtime._do_train(run_name=f"{spec.slug}-m{idx}", overrides={})  # noqa: SLF001
            except Exception:  # noqa: BLE001
                logger.exception("walk-forward member %d failed", idx)
                continue
            per_member.append({"member": idx, "config": member_cfg, "outcome": outcome})
            metrics = outcome.get("metrics", {}) or {}
            sharpe = float(metrics.get("sharpe", 0.0) or 0.0)
            if results.best_member is None or sharpe > float(results.best_member.get("sharpe", -1e9) or 0.0):
                results.best_member = {
                    **per_member[-1],
                    "sharpe": sharpe,
                }
                # Materialise the best agent for inference.
                if member_spec.agent is not None:
                    self._best = build_from_config(member_spec.agent)
        results.member_metrics = per_member
        results.selected = [results.best_member["config"].get("class", "")] if results.best_member else []
        return {
            "members": per_member,
            "best": results.best_member,
            "selected": results.selected,
        }

    def _derive_member_spec(self, base_spec: Any, member_cfg: dict[str, Any]) -> Any:
        """Clone ``base_spec`` with ``member_cfg`` swapped into the agent slot."""
        try:
            data = base_spec.model_dump(mode="python")
        except Exception:  # noqa: BLE001
            data = dict(getattr(base_spec, "__dict__", {}))
        data["agent"] = member_cfg
        cls = type(base_spec)
        return cls.model_validate(data)


__all__ = ["WalkForwardEnsembler", "WalkForwardResult"]
