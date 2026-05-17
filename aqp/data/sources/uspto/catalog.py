"""Postgres upsert helpers for USPTO rows."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aqp.persistence.db import SessionLocal

logger = logging.getLogger(__name__)


def _to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _join_inventors(payload: dict[str, Any]) -> list[str]:
    inventors = payload.get("inventors") or []
    out: list[str] = []
    for inv in inventors:
        if not isinstance(inv, dict):
            continue
        first = inv.get("inventor_name_first") or inv.get("name_first") or ""
        last = inv.get("inventor_name_last") or inv.get("name_last") or ""
        full = f"{first} {last}".strip()
        if full:
            out.append(full)
    return out


def upsert_uspto_patent(payload: dict[str, Any]) -> None:
    try:
        from aqp.persistence.models_regulatory import UsptoPatent
    except Exception:  # pragma: no cover
        return
    pno = str(payload.get("patent_id") or payload.get("patent_number") or "").strip()
    if not pno:
        return
    assignees = payload.get("assignees") or []
    assignee = ""
    if assignees and isinstance(assignees, list):
        assignee = (assignees[0] or {}).get("assignee_organization") or ""
    application = payload.get("application") or {}
    if isinstance(application, list):
        application = application[0] if application else {}
    fields = {
        "patent_number": pno,
        "title": payload.get("patent_title") or "",
        "abstract": payload.get("patent_abstract") or "",
        "filing_date": _to_dt(application.get("filing_date") if isinstance(application, dict) else None),
        "grant_date": _to_dt(payload.get("patent_date")),
        "assignee": str(assignee).strip(),
        "inventors": _join_inventors(payload),
        "classification": (payload.get("cpc_current") or [{}])[0].get("cpc_subgroup_id", "") if payload.get("cpc_current") else "",
        "application_number": application.get("application_number") if isinstance(application, dict) else None,
        "citation_count": int(payload.get("patent_num_us_patent_citations") or 0) if payload.get("patent_num_us_patent_citations") else None,
        "vt_symbol": payload.get("vt_symbol") or "",
        "raw": payload,
    }
    try:
        with SessionLocal() as session:
            existing = session.query(UsptoPatent).filter(UsptoPatent.patent_number == pno).one_or_none()
            if existing is None:
                session.add(UsptoPatent(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to upsert USPTO patent %s", pno)


def upsert_uspto_trademark(payload: dict[str, Any]) -> None:
    try:
        from aqp.persistence.models_regulatory import UsptoTrademark
    except Exception:  # pragma: no cover
        return
    sn = str(payload.get("serial_number") or payload.get("serialNumber") or "").strip()
    if not sn:
        return
    fields = {
        "serial_number": sn,
        "registration_number": payload.get("registration_number") or payload.get("registrationNumber") or "",
        "mark_text": payload.get("mark_text") or payload.get("markText") or "",
        "owner": payload.get("owner") or payload.get("ownerName") or "",
        "status": payload.get("status") or payload.get("caseStatus") or "",
        "filing_date": _to_dt(payload.get("filing_date") or payload.get("filingDate")),
        "registration_date": _to_dt(payload.get("registration_date") or payload.get("registrationDate")),
        "abandonment_date": _to_dt(payload.get("abandonment_date")),
        "class_codes": payload.get("class_codes") or payload.get("classCodes") or "",
        "description": payload.get("description") or "",
        "vt_symbol": payload.get("vt_symbol") or "",
        "raw": payload,
    }
    try:
        with SessionLocal() as session:
            existing = (
                session.query(UsptoTrademark).filter(UsptoTrademark.serial_number == sn).one_or_none()
            )
            if existing is None:
                session.add(UsptoTrademark(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to upsert USPTO trademark %s", sn)


def upsert_uspto_assignment(payload: dict[str, Any]) -> None:
    try:
        from aqp.persistence.models_regulatory import UsptoAssignment
    except Exception:  # pragma: no cover
        return
    aid = str(payload.get("assignment_id") or payload.get("recordationNumber") or "").strip()
    if not aid:
        return
    fields = {
        "assignment_id": aid,
        "recorded_date": _to_dt(payload.get("recorded_date") or payload.get("recordedDate")),
        "execution_date": _to_dt(payload.get("execution_date") or payload.get("executionDate")),
        "conveyance_text": payload.get("conveyance_text") or payload.get("conveyanceText") or "",
        "assignor": payload.get("assignor") or "",
        "assignee": payload.get("assignee") or "",
        "patents": payload.get("patents") or "",
        "vt_symbol": payload.get("vt_symbol") or "",
        "raw": payload,
    }
    try:
        with SessionLocal() as session:
            existing = (
                session.query(UsptoAssignment).filter(UsptoAssignment.assignment_id == aid).one_or_none()
            )
            if existing is None:
                session.add(UsptoAssignment(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to upsert USPTO assignment %s", aid)


__all__ = [
    "upsert_uspto_assignment",
    "upsert_uspto_patent",
    "upsert_uspto_trademark",
]
