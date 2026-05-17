"""``CrewProcessAdapter`` — wraps CrewAI crews behind the adapter contract.

Routes to one of the two existing crew factories in this repo:

- :func:`aqp.agents.crew.run_research_crew` for the six-stage research
  crew defined by ``configs/agents/research_crew.yaml``.
- :func:`aqp.agents.trading.crew.run_trader_crew` for the trader crew
  (Bull/Bear debate + Risk + Portfolio Manager).

Both factories use CrewAI's ``Process.sequential`` / ``Process.hierarchical``
internally; the adapter honours whichever mode the underlying YAML
declares without re-implementing the loop.

Optional dep
------------
CrewAI is an optional extra. When the import fails the adapter
returns ``status="error"`` with a ``failure.kind="error"`` payload so
the runtime can still record a clean failure breadcrumb instead of
crashing the worker.

Gating
------
The adapter only auto-activates when
``settings.orchestration_crew_adapter_enabled`` is ``True``. The class
itself still imports and registers (so the studio dropdown can show
it greyed out), but :meth:`invoke` short-circuits to a policy-style
failure when the flag is off.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from aqp.agents.orchestration.base import OrchestrationAdapter
from aqp.agents.orchestration.types import (
    AdapterContext,
    AdapterFailure,
    AdapterResult,
)
from aqp.config import settings

logger = logging.getLogger(__name__)


_CREW_FACTORIES: dict[str, str] = {
    "research": "aqp.agents.crew:run_research_crew",
    "trader": "aqp.agents.trading.crew:run_trader_crew",
}


class CrewProcessAdapter(OrchestrationAdapter):
    """Wraps CrewAI sequential / hierarchical crews.

    Spec contract::

        adapter: CrewProcessAdapter
        params:
          crew: research                  # one of _CREW_FACTORIES
          user_prompt: "..."              # forwarded into the crew kickoff
          config_path: null               # optional override of default YAML
          inputs: {}                      # extra kwargs forwarded
    """

    adapter_kind = "crew"
    adapter_alias = "CrewProcessAdapter"
    adapter_source = "finrobot"
    adapter_category = "crew"
    adapter_tags = ("crewai", "sequential", "hierarchical")

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        start = time.perf_counter()
        if not getattr(settings, "orchestration_crew_adapter_enabled", False):
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(
                    message=(
                        "CrewProcessAdapter requires "
                        "AQP_ORCHESTRATION_CREW_ADAPTER_ENABLED=true"
                    ),
                    kind="policy",
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        params = context.extras.get("params") or {}
        crew_alias = str(params.get("crew") or "research")
        if crew_alias not in _CREW_FACTORIES:
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(
                    message=(
                        f"unknown crew alias {crew_alias!r}; "
                        f"expected one of {sorted(_CREW_FACTORIES)}"
                    ),
                    kind="error",
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        user_prompt = str(params.get("user_prompt") or state.get("inputs", {}).get("prompt") or "")
        config_path = params.get("config_path")
        crew_inputs: dict[str, Any] = dict(params.get("inputs") or {})

        try:
            run_fn = self._resolve_crew_factory(crew_alias)
        except Exception as exc:  # noqa: BLE001
            logger.debug("CrewProcessAdapter import failed", exc_info=True)
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(
                    message=f"crew factory import failed: {exc}", kind="error"
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        # Halt-check before kickoff so we never start a long crew when
        # the kill switch is already flipped.
        if context.is_halted():
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_HALTED,
                failure=AdapterFailure(
                    message="halt_check fired before crew kickoff", kind="halted"
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        try:
            kwargs: dict[str, Any] = {}
            if config_path:
                kwargs["config_path"] = Path(str(config_path))
            if crew_inputs:
                kwargs["inputs"] = crew_inputs
            result = run_fn(user_prompt, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("CrewProcessAdapter kickoff failed for %s", crew_alias)
            return AdapterResult(
                state=state,
                status=AdapterResult.STATUS_ERROR,
                failure=AdapterFailure(message=str(exc), kind="error"),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        merged = dict(state)
        merged.setdefault("crew_outputs", {})
        merged["crew_outputs"][crew_alias] = result
        breadcrumb = {
            "adapter": self.adapter_alias,
            "node": f"crew:{crew_alias}",
            "status": "ok",
            "duration_ms": round((time.perf_counter() - start) * 1000.0, 3),
        }
        existing_breadcrumbs = list(merged.get("adapter_breadcrumbs") or [])
        merged["adapter_breadcrumbs"] = existing_breadcrumbs + [breadcrumb]
        return AdapterResult(
            state=merged,
            status=AdapterResult.STATUS_COMPLETED,
            breadcrumbs=[breadcrumb],
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    # ------------------------------------------------------------------ helpers
    def _resolve_crew_factory(self, crew_alias: str) -> Any:
        """Import the underlying ``run_*_crew`` function lazily.

        Defers the CrewAI import to the call site so cold installs
        without the dep can still boot the orchestration package.
        """
        target = _CREW_FACTORIES[crew_alias]
        module_path, fn_name = target.split(":", 1)
        import importlib

        mod = importlib.import_module(module_path)
        return getattr(mod, fn_name)


__all__ = ["CrewProcessAdapter"]
