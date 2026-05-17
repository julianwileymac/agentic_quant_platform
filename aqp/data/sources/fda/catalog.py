"""Postgres upsert helpers for FDA rows."""
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
    s = str(value)
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def upsert_fda_application(payload: dict[str, Any]) -> None:
    try:
        from aqp.persistence.models_regulatory import FdaApplication
    except Exception:  # pragma: no cover
        return
    appno = str(payload.get("application_number") or payload.get("application_no") or "").strip()
    if not appno:
        return
    products = payload.get("products") or []
    drug_name = ""
    indication = ""
    if products and isinstance(products, list):
        drug_name = (products[0] or {}).get("brand_name") or (products[0] or {}).get("active_ingredients", [{}])[0].get("name", "") if products else ""
    submissions = payload.get("submissions") or []
    submission_date = None
    submission_status = None
    if submissions and isinstance(submissions, list):
        submission_date = _to_dt((submissions[0] or {}).get("submission_status_date"))
        submission_status = (submissions[0] or {}).get("submission_status")
    fields = {
        "application_number": appno,
        "application_type": payload.get("application_type") or payload.get("submission_type") or "",
        "sponsor_name": str(payload.get("sponsor_name") or payload.get("applicant") or "").strip(),
        "drug_name": drug_name or "",
        "indication": indication or "",
        "submission_status": submission_status or "",
        "submission_date": submission_date,
        "approval_date": _to_dt(payload.get("approval_date") or payload.get("decision_date")),
        "review_priority": payload.get("review_priority") or "",
        "therapeutic_area": payload.get("openfda", {}).get("pharm_class_epc", [None])[0] if payload.get("openfda") else "",
        "vt_symbol": payload.get("vt_symbol") or "",
        "raw": payload,
    }
    try:
        with SessionLocal() as session:
            existing = (
                session.query(FdaApplication)
                .filter(FdaApplication.application_number == appno)
                .one_or_none()
            )
            if existing is None:
                session.add(FdaApplication(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to upsert FDA application %s", appno)


def upsert_fda_adverse_event(payload: dict[str, Any], *, source: str = "faers") -> None:
    try:
        from aqp.persistence.models_regulatory import FdaAdverseEvent
    except Exception:  # pragma: no cover
        return
    rid = str(payload.get("safetyreportid") or payload.get("mdr_report_key") or payload.get("report_id") or "").strip()
    if not rid:
        return
    patient = payload.get("patient") or {}
    drugs = patient.get("drug") if isinstance(patient, dict) else None
    reactions = patient.get("reaction") if isinstance(patient, dict) else None
    product_name = ""
    manufacturer_name = ""
    if drugs and isinstance(drugs, list):
        first = drugs[0] or {}
        product_name = first.get("medicinalproduct") or ""
        openfda = first.get("openfda") or {}
        if isinstance(openfda, dict):
            manufacturer_name = (openfda.get("manufacturer_name") or [""])[0]
    reactions_text = ""
    outcomes_text = ""
    if reactions and isinstance(reactions, list):
        reactions_text = "; ".join(
            (r or {}).get("reactionmeddrapt", "") for r in reactions if r
        )
        outcomes_text = "; ".join(
            str((r or {}).get("reactionoutcome", "")) for r in reactions if r
        )
    fields = {
        "report_id": rid,
        "received_date": _to_dt(payload.get("receivedate") or payload.get("date_received")),
        "product_name": product_name or "",
        "manufacturer_name": manufacturer_name or "",
        "reactions": reactions_text,
        "outcomes": outcomes_text,
        "is_serious": str(payload.get("serious", "")).lower() in {"1", "true"},
        "patient_age": float(patient.get("patientonsetage", 0) or 0) if isinstance(patient, dict) else None,
        "patient_sex": str(patient.get("patientsex", "")) if isinstance(patient, dict) else "",
        "country": payload.get("occurcountry") or payload.get("country") or "",
        "source": source,
        "vt_symbol": payload.get("vt_symbol") or "",
        "raw": payload,
    }
    try:
        with SessionLocal() as session:
            existing = (
                session.query(FdaAdverseEvent)
                .filter(FdaAdverseEvent.report_id == rid)
                .one_or_none()
            )
            if existing is None:
                session.add(FdaAdverseEvent(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to upsert FDA adverse event %s", rid)


def upsert_fda_recall(payload: dict[str, Any], *, product_type: str = "drug") -> None:
    try:
        from aqp.persistence.models_regulatory import FdaRecall
    except Exception:  # pragma: no cover
        return
    rno = str(payload.get("recall_number") or "").strip()
    if not rno:
        return
    fields = {
        "recall_number": rno,
        "recalling_firm": str(payload.get("recalling_firm") or "").strip(),
        "classification": payload.get("classification") or "",
        "status": payload.get("status") or "",
        "product_description": payload.get("product_description") or "",
        "reason_for_recall": payload.get("reason_for_recall") or "",
        "code_info": payload.get("code_info") or "",
        "distribution_pattern": payload.get("distribution_pattern") or "",
        "voluntary_mandated": payload.get("voluntary_mandated") or "",
        "initial_firm_notification": payload.get("initial_firm_notification") or "",
        "recall_initiation_date": _to_dt(payload.get("recall_initiation_date")),
        "report_date": _to_dt(payload.get("report_date")),
        "termination_date": _to_dt(payload.get("termination_date")),
        "product_type": product_type,
        "vt_symbol": payload.get("vt_symbol") or "",
        "raw": payload,
    }
    try:
        with SessionLocal() as session:
            existing = (
                session.query(FdaRecall).filter(FdaRecall.recall_number == rno).one_or_none()
            )
            if existing is None:
                session.add(FdaRecall(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to upsert FDA recall %s", rno)


__all__ = [
    "upsert_fda_adverse_event",
    "upsert_fda_application",
    "upsert_fda_recall",
]
