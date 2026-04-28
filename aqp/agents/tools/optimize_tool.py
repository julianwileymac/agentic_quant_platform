"""CrewAI tool: emit a structured optimisation proposal.

Used by the analysis-agent team to write actionable suggestions
("increase position cap", "tighten ATR multiple") into
``agent_annotations`` for downstream backtest-grid runners.
"""
from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class OptimizeProposalInput(BaseModel):
    spec_name: str
    target: str = Field(..., description="What is being optimised (strategy/model id)")
    suggestions: list[str] = Field(
        ..., description="Actionable proposals (max 5)", max_length=5
    )
    expected_lift: float | None = Field(default=None, description="Expected improvement, eg Sharpe")
    rationale: str = ""


class OptimizeProposalTool(BaseTool):
    name: str = "optimize_proposal"
    description: str = (
        "Persist a structured optimisation proposal "
        "(target + suggestions + expected lift) for the next research cycle."
    )
    args_schema: type[BaseModel] = OptimizeProposalInput

    def _run(  # type: ignore[override]
        self,
        spec_name: str,
        target: str,
        suggestions: list[str],
        expected_lift: float | None = None,
        rationale: str = "",
    ) -> str:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_agents import AgentAnnotation

            with SessionLocal() as session:
                row = AgentAnnotation(
                    spec_name=spec_name,
                    label="optimize_proposal",
                    notes=rationale,
                    payload={
                        "target": target,
                        "suggestions": list(suggestions or []),
                        "expected_lift": expected_lift,
                    },
                )
                session.add(row)
                session.commit()
                return f"proposal stored id={row.id}"
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: optimize_proposal persist failed: {exc}"


__all__ = ["OptimizeProposalTool"]
