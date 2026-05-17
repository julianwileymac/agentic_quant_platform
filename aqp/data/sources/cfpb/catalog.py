"""Postgres upsert helpers for CFPB rows."""
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
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def upsert_cfpb_complaint(payload: dict[str, Any]) -> None:
    """Insert or update one CFPB complaint row in Postgres."""
    try:
        from aqp.persistence.models_regulatory import CfpbComplaint
    except Exception:  # pragma: no cover
        logger.debug("CfpbComplaint table missing; skip upsert.", exc_info=True)
        return
    cid = str(payload.get("complaint_id") or payload.get("complaintId") or "").strip()
    if not cid:
        return
    narrative = payload.get("complaint_what_happened") or payload.get("consumer_complaint_narrative")
    fields = {
        "complaint_id": cid,
        "company": str(payload.get("company") or "").strip(),
        "company_response": payload.get("company_response_to_consumer") or payload.get("company_response"),
        "consumer_consent_provided": payload.get("consumer_consent_provided") or "",
        "consumer_complaint_narrative": narrative or "",
        "date_received": _to_dt(payload.get("date_received") or payload.get("dateReceived")),
        "date_sent_to_company": _to_dt(payload.get("date_sent_to_company")),
        "issue": payload.get("issue") or "",
        "sub_issue": payload.get("sub_issue") or "",
        "product": payload.get("product") or "",
        "sub_product": payload.get("sub_product") or "",
        "state": payload.get("state") or "",
        "zip_code": payload.get("zip_code") or "",
        "submitted_via": payload.get("submitted_via") or "",
        "tags": payload.get("tags") or "",
        "timely": payload.get("timely") or "",
        "has_narrative": bool(narrative),
        "vt_symbol": payload.get("vt_symbol") or "",
        "raw": payload,
    }
    try:
        with SessionLocal() as session:
            existing = (
                session.query(CfpbComplaint)
                .filter(CfpbComplaint.complaint_id == cid)
                .one_or_none()
            )
            if existing is None:
                session.add(CfpbComplaint(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to upsert CFPB complaint %s", cid)


__all__ = ["upsert_cfpb_complaint"]
