"""CrewAI tool: cross-source regulatory lookup (CFPB / FDA / USPTO)."""
from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class RegulatoryLookupInput(BaseModel):
    company: str = Field(..., description="Issuer / sponsor / firm / assignee name")
    sources: list[str] = Field(
        default_factory=lambda: ["cfpb", "fda", "uspto"],
        description="Subset of cfpb|fda|uspto",
    )
    limit: int = Field(default=20, ge=1, le=200)


class RegulatoryLookupTool(BaseTool):
    name: str = "regulatory_lookup"
    description: str = (
        "Look up curated CFPB / FDA / USPTO rows for a company. "
        "Returns the most recent records across requested sources."
    )
    args_schema: type[BaseModel] = RegulatoryLookupInput

    def _run(  # type: ignore[override]
        self,
        company: str,
        sources: list[str] | None = None,
        limit: int = 20,
    ) -> str:
        sources = [s.lower() for s in (sources or ["cfpb", "fda", "uspto"])]
        out: list[str] = []
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_regulatory import (
                CfpbComplaint,
                FdaApplication,
                FdaRecall,
                UsptoPatent,
                UsptoTrademark,
            )
        except Exception as exc:  # noqa: BLE001
            return f"ERROR: regulatory tables unavailable: {exc}"

        with SessionLocal() as session:
            if "cfpb" in sources:
                rows = (
                    session.query(CfpbComplaint)
                    .filter(CfpbComplaint.company == company)
                    .order_by(CfpbComplaint.date_received.desc())
                    .limit(limit)
                    .all()
                )
                for r in rows:
                    out.append(
                        f"[CFPB {r.date_received}] {r.product or '?'} / {r.issue or '?'}: "
                        f"{(r.consumer_complaint_narrative or '')[:160]}"
                    )
            if "fda" in sources:
                apps = (
                    session.query(FdaApplication)
                    .filter(FdaApplication.sponsor_name == company)
                    .order_by(FdaApplication.submission_date.desc())
                    .limit(limit)
                    .all()
                )
                for r in apps:
                    out.append(
                        f"[FDA app {r.application_number}] {r.application_type or '?'} "
                        f"drug={r.drug_name or '?'} status={r.submission_status or '?'} "
                        f"date={r.submission_date}"
                    )
                rec = (
                    session.query(FdaRecall)
                    .filter(FdaRecall.recalling_firm == company)
                    .order_by(FdaRecall.recall_initiation_date.desc())
                    .limit(limit)
                    .all()
                )
                for r in rec:
                    out.append(
                        f"[FDA recall {r.recall_number}] class={r.classification} "
                        f"reason={(r.reason_for_recall or '')[:120]}"
                    )
            if "uspto" in sources:
                pats = (
                    session.query(UsptoPatent)
                    .filter(UsptoPatent.assignee == company)
                    .order_by(UsptoPatent.grant_date.desc())
                    .limit(limit)
                    .all()
                )
                for r in pats:
                    out.append(
                        f"[USPTO patent {r.patent_number}] grant={r.grant_date} "
                        f"title={(r.title or '')[:120]}"
                    )
                tms = (
                    session.query(UsptoTrademark)
                    .filter(UsptoTrademark.owner == company)
                    .order_by(UsptoTrademark.filing_date.desc())
                    .limit(limit)
                    .all()
                )
                for r in tms:
                    out.append(
                        f"[USPTO trademark {r.serial_number}] mark={r.mark_text} "
                        f"status={r.status} filed={r.filing_date}"
                    )
        if not out:
            return f"No regulatory hits for {company}."
        return "\n".join(out[: limit * 3])


__all__ = ["RegulatoryLookupTool"]
