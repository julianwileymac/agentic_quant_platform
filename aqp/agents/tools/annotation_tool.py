"""CrewAI tool: write structured annotations for optimisation analysis."""
from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class AnnotationInput(BaseModel):
    spec_name: str
    label: str = Field(..., description="Short label, e.g. 'pick_rationale'")
    notes: str | None = None
    vt_symbol: str | None = None
    run_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AnnotationTool(BaseTool):
    name: str = "annotation"
    description: str = (
        "Persist a structured annotation against an agent run / symbol "
        "(used by Selection + Analysis agents for downstream optimisation)."
    )
    args_schema: type[BaseModel] = AnnotationInput

    def _run(  # type: ignore[override]
        self,
        spec_name: str,
        label: str,
        notes: str | None = None,
        vt_symbol: str | None = None,
        run_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_agents import AgentAnnotation

            with SessionLocal() as session:
                row = AgentAnnotation(
                    spec_name=spec_name,
                    run_id=run_id,
                    vt_symbol=vt_symbol,
                    label=label,
                    notes=notes,
                    payload=payload or {},
                )
                session.add(row)
                session.commit()
                return f"annotation persisted id={row.id}"
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: annotation persist failed: {exc}"


__all__ = ["AnnotationTool"]
