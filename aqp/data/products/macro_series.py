"""Macro series entity-centric data product."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from aqp.data.products.base import BaseDataProduct, DataProductError
from aqp.persistence.db import get_session

logger = logging.getLogger(__name__)


class MacroSeriesEntity(BaseDataProduct):
    """Pre-aggregated view of one macroeconomic series.

    ``series_id`` is the FRED / BLS / Treasury identifier (eg.
    ``"FRED:DGS10"``). Loads the latest N observations plus the
    underlying :class:`EconomicSeriesRow` metadata (frequency, units,
    description).
    """

    product_kind = "macro_series"

    def __init__(
        self,
        series_id: str,
        *,
        as_of: datetime | None = None,
        recent_observations: int = 60,
    ) -> None:
        super().__init__(entity_id=series_id, as_of=as_of)
        self.series_id = str(series_id)
        self.recent_observations = max(int(recent_observations), 1)

    def load(self) -> None:
        try:
            from aqp.persistence.models_macro import (
                EconomicObservation,
                EconomicSeriesRow,
            )
        except ImportError as exc:
            raise DataProductError("macro tables unavailable") from exc

        with get_session() as session:
            series_row = (
                session.execute(
                    select(EconomicSeriesRow).where(
                        EconomicSeriesRow.series_id == self.series_id
                    )
                )
                .scalars()
                .first()
            )
            if series_row is None:
                raise DataProductError(f"unknown macro series {self.series_id!r}")
            self._payload["series"] = {
                "series_id": series_row.series_id,
                "source": getattr(series_row, "source", None),
                "title": getattr(series_row, "title", None),
                "units": getattr(series_row, "units", None),
                "frequency": getattr(series_row, "frequency", None),
                "seasonal_adjustment": getattr(series_row, "seasonal_adjustment", None),
                "description": getattr(series_row, "description", None),
                "last_updated": _coerce_datetime(getattr(series_row, "last_updated", None)),
            }

            try:
                rows = (
                    session.execute(
                        select(EconomicObservation)
                        .where(EconomicObservation.series_id == self.series_id)
                        .order_by(desc(EconomicObservation.observation_date))
                        .limit(self.recent_observations)
                    )
                    .scalars()
                    .all()
                )
            except Exception:  # noqa: BLE001
                rows = []
            self._payload["observations"] = [
                {
                    "observation_date": _coerce_datetime(
                        getattr(row, "observation_date", None)
                    ),
                    "value": getattr(row, "value", None),
                }
                for row in rows
            ]

        self.add_provenance_source(
            getattr(series_row, "source", None) or "macro_series_provider"
        )
        self.add_lineage(
            transform_kind="data_product_load",
            target_table_id=None,
            summary=f"loaded macro series {self.series_id}",
            actor=self.product_kind,
        )


def _coerce_datetime(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


__all__ = ["MacroSeriesEntity"]
