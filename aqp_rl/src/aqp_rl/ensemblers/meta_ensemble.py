"""``MetaEnsembleRunner`` — weight-blend over multiple trained agents."""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np

from aqp_rl.core.ensembler import BaseEnsembler

logger = logging.getLogger(__name__)


class MetaEnsembleRunner(BaseEnsembler):
    """Run multiple agents in parallel and blend their actions by ``weights``."""

    rl_alias: ClassVar[str] = "MetaEnsembleRunner"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "meta"
    rl_tags: ClassVar[tuple[str, ...]] = ("ensemble", "blend")

    def __init__(
        self,
        *,
        members: list[dict[str, Any]],
        weights: list[float] | None = None,
    ) -> None:
        super().__init__()
        self.members = list(members or [])
        self.weights = list(weights or [1.0 / max(len(self.members), 1)] * len(self.members))
        self._built: list[Any] = []

    def train(self, spec: Any, runtime: Any) -> dict[str, Any]:
        from aqp.core.registry import build_from_config

        results: list[dict[str, Any]] = []
        self._built = []
        for idx, member_cfg in enumerate(self.members):
            try:
                derived = self._derive_member_spec(spec, member_cfg)
                runtime.spec = derived
                outcome = runtime._do_train(run_name=f"{spec.slug}-m{idx}", overrides={})  # noqa: SLF001
                results.append({"member": idx, "config": member_cfg, "outcome": outcome})
                if derived.agent is not None:
                    self._built.append(build_from_config(derived.agent))
            except Exception:  # noqa: BLE001
                logger.exception("meta-ensemble member %d failed", idx)
        return {"members": results, "weights": self.weights}

    def _derive_member_spec(self, base_spec: Any, member_cfg: dict[str, Any]) -> Any:
        try:
            data = base_spec.model_dump(mode="python")
        except Exception:  # noqa: BLE001
            data = dict(getattr(base_spec, "__dict__", {}))
        data["agent"] = member_cfg
        cls = type(base_spec)
        return cls.model_validate(data)

    def predict(self, obs: Any, deterministic: bool = True) -> Any:
        if not self._built:
            raise RuntimeError("MetaEnsembleRunner has no trained members yet — call train() first.")
        actions = []
        for agent in self._built:
            try:
                action, _ = agent.predict(obs, deterministic=deterministic)
                actions.append(np.asarray(action, dtype=np.float32))
            except Exception:  # noqa: BLE001
                continue
        if not actions:
            raise RuntimeError("All ensemble members failed to predict.")
        weights = np.asarray(self.weights[: len(actions)], dtype=np.float32)
        weights = weights / max(weights.sum(), 1e-9)
        stacked = np.stack(actions, axis=0)
        blended = np.einsum("i,i...->...", weights, stacked)
        return blended, None


__all__ = ["MetaEnsembleRunner"]
