"""Concrete :class:`OrchestrationAdapter` implementations.

Each adapter subclasses :class:`aqp.agents.orchestration.
OrchestrationAdapter` and self-registers via the metaclass on import.
Heavy optional deps (``langgraph`` / ``crewai`` / ``pyiceberg``) stay
inside each adapter's :meth:`invoke` body so a cold install missing
those packages can still import the registry and surface the adapter
as a greyed-out option in the studio.

Phase 2 ships three adapters:

- :class:`LangGraphAdapter` (graph) — wraps the five canonical
  builders in :mod:`aqp.agents.graph.builder` + the dialectical
  builder.
- :class:`CrewProcessAdapter` (crew) — wraps the existing
  ``run_research_crew`` and ``run_trader_crew`` factories.
- :class:`DialecticalDebateAdapter` (debate) — bounded TradingAgents
  Bull/Bear/PortfolioManager debate with forced judge synthesis.

Phase 3 adds :class:`AutomationScheduleAdapter`; Phase 4 adds
:class:`SignalFusionAdapter` + :class:`WeightCentricExecutionAdapter`;
Phase 5 adds :class:`WorkflowStudioAdapter`.
"""
from __future__ import annotations

from aqp.agents.orchestration.adapters.crew_adapter import CrewProcessAdapter
from aqp.agents.orchestration.adapters.debate_adapter import DialecticalDebateAdapter
from aqp.agents.orchestration.adapters.evolutionary_debate import (
    EvolutionaryDebateAdapter,
)
from aqp.agents.orchestration.adapters.fusion_adapter import SignalFusionAdapter
from aqp.agents.orchestration.adapters.langgraph_adapter import LangGraphAdapter
from aqp.agents.orchestration.adapters.schedule_adapter import (
    AutomationScheduleAdapter,
    beat_key_for_spec,
    register_schedule_with_celery_beat,
)
from aqp.agents.orchestration.adapters.weight_centric_adapter import (
    WeightCentricExecutionAdapter,
)

__all__ = [
    "AutomationScheduleAdapter",
    "CrewProcessAdapter",
    "DialecticalDebateAdapter",
    "EvolutionaryDebateAdapter",
    "LangGraphAdapter",
    "SignalFusionAdapter",
    "WeightCentricExecutionAdapter",
    "beat_key_for_spec",
    "register_schedule_with_celery_beat",
]
