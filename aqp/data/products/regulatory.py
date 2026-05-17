"""Regulatory entity-centric data product (CFPB / FDA / USPTO)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from aqp.data.products.base import BaseDataProduct
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)


class RegulatoryEntity(BaseDataProduct):
    """Aggregated CFPB / FDA / USPTO mentions for one ``vt_symbol``.

    Pulls the latest few rows from each regulatory table so the LLM
    has a token-efficient summary of regulatory exposure for an
    instrument. Detail queries route through dedicated MCP tools.
    """

    product_kind = "regulatory"

    def __init__(
        self,
        vt_symbol: str,
        *,
        as_of: datetime | None = None,
        per_table_limit: int = 10,
    ) -> None:
        super().__init__(entity_id=vt_symbol, as_of=as_of)
        self.vt_symbol = str(vt_symbol)
        self.per_table_limit = max(int(per_table_limit), 1)

    def load(self) -> None:
        with get_session() as session:
            self._payload["cfpb"] = self._lookup_cfpb(session)
            self._payload["fda"] = self._lookup_fda(session)
            self._payload["uspto"] = self._lookup_uspto(session)

        self.add_provenance_source("cfpb")
        self.add_provenance_source("fda")
        self.add_provenance_source("uspto")
        self.add_lineage(
            transform_kind="data_product_load",
            target_table_id=None,
            summary=f"loaded regulatory entity for {self.vt_symbol}",
            actor=self.product_kind,
        )

    def _lookup_cfpb(self, session) -> list[dict[str, Any]]:
        try:
            from aqp.persistence.models_regulatory import CfpbComplaint
        except ImportError:
            return []
        try:
            rows = (
                session.execute(
                    select(CfpbComplaint)
                    .where(CfpbComplaint.vt_symbol == self.vt_symbol)
                    .order_by(desc(CfpbComplaint.date_received))
                    .limit(self.per_table_limit)
                )
                .scalars()
                .all()
            )
        except Exception:  # noqa: BLE001
            return []
        return [
            {
                "complaint_id": getattr(row, "complaint_id", None),
                "product": getattr(row, "product", None),
                "issue": getattr(row, "issue", None),
                "submitting_party": getattr(row, "submitting_party", None),
                "company": getattr(row, "company", None),
                "date_received": _coerce_datetime(getattr(row, "date_received", None)),
                "company_response": getattr(row, "company_response", None),
            }
            for row in rows
        ]

    def _lookup_fda(self, session) -> dict[str, Any]:
        try:
            from aqp.persistence.models_regulatory import (
                FdaAdverseEvent,
                FdaApplication,
                FdaRecall,
            )
        except ImportError:
            return {}
        out: dict[str, Any] = {}
        for table_cls, key in (
            (FdaApplication, "applications"),
            (FdaAdverseEvent, "adverse_events"),
            (FdaRecall, "recalls"),
        ):
            try:
                rows = (
                    session.execute(
                        select(table_cls)
                        .where(getattr(table_cls, "vt_symbol") == self.vt_symbol)
                        .order_by(desc(getattr(table_cls, "id")))
                        .limit(self.per_table_limit)
                    )
                    .scalars()
                    .all()
                )
            except Exception:  # noqa: BLE001
                rows = []
            out[key] = [_orm_to_summary_row(row) for row in rows]
        return out

    def _lookup_uspto(self, session) -> dict[str, Any]:
        try:
            from aqp.persistence.models_regulatory import (
                UsptoAssignment,
                UsptoPatent,
                UsptoTrademark,
            )
        except ImportError:
            return {}
        out: dict[str, Any] = {}
        for table_cls, key in (
            (UsptoPatent, "patents"),
            (UsptoTrademark, "trademarks"),
            (UsptoAssignment, "assignments"),
        ):
            try:
                rows = (
                    session.execute(
                        select(table_cls)
                        .where(getattr(table_cls, "vt_symbol") == self.vt_symbol)
                        .order_by(desc(getattr(table_cls, "id")))
                        .limit(self.per_table_limit)
                    )
                    .scalars()
                    .all()
                )
            except Exception:  # noqa: BLE001
                rows = []
            out[key] = [_orm_to_summary_row(row) for row in rows]
        return out


def _orm_to_summary_row(row: Any) -> dict[str, Any]:
    """Best-effort dict snapshot of a regulatory row.

    Keeps only string / number / date attributes to stay token-friendly.
    """
    if row is None:
        return {}
    out: dict[str, Any] = {}
    for attr in dir(row):
        if attr.startswith("_") or attr in {"metadata", "registry"}:
            continue
        try:
            value = getattr(row, attr)
        except Exception:  # noqa: BLE001
            continue
        if callable(value):
            continue
        if isinstance(value, (str, int, float, bool)):
            out[attr] = value
        elif hasattr(value, "isoformat"):
            out[attr] = value.isoformat()
    # Drop tenancy / housekeeping columns
    for noisy_key in (
        "owner_user_id",
        "workspace_id",
        "project_id",
        "lab_id",
        "created_at",
        "updated_at",
        "_workspace_id",
        "_project_id",
    ):
        out.pop(noisy_key, None)
    return out


def _coerce_datetime(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


__all__ = ["RegulatoryEntity"]
