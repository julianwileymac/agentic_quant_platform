"""Option chain entity-centric data product."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select

from aqp.data.products.base import BaseDataProduct, DataProductError
from aqp.persistence.db import get_session
from aqp.persistence.models import Instrument

logger = logging.getLogger(__name__)


class OptionChainEntity(BaseDataProduct):
    """Latest option chain snapshot for one underlying ``vt_symbol``."""

    product_kind = "option_chain"

    def __init__(
        self,
        vt_symbol: str,
        *,
        as_of: datetime | None = None,
        max_strikes: int = 50,
    ) -> None:
        super().__init__(entity_id=vt_symbol, as_of=as_of)
        self.vt_symbol = str(vt_symbol)
        self.max_strikes = max(int(max_strikes), 1)

    def load(self) -> None:
        try:
            from aqp.persistence.models_macro import (
                OptionChainSnapshot,
                OptionSeries,
            )
        except ImportError as exc:  # pragma: no cover
            raise DataProductError(
                "OptionChainSnapshot model unavailable"
            ) from exc

        with get_session() as session:
            instrument = (
                session.execute(
                    select(Instrument).where(Instrument.vt_symbol == self.vt_symbol)
                )
                .scalars()
                .first()
            )
            if instrument is None:
                raise DataProductError(
                    f"no instrument with vt_symbol={self.vt_symbol!r}"
                )
            self._payload["underlying"] = {
                "vt_symbol": instrument.vt_symbol,
                "ticker": instrument.ticker,
                "exchange": instrument.exchange,
                "currency": instrument.currency,
                "instrument_id": instrument.id,
            }

            try:
                snapshots = (
                    session.execute(
                        select(OptionChainSnapshot)
                        .where(
                            OptionChainSnapshot.underlying_instrument_id == instrument.id
                        )
                        .order_by(desc(OptionChainSnapshot.snapshot_ts))
                        .limit(1)
                    )
                    .scalars()
                    .all()
                )
            except Exception:  # noqa: BLE001
                snapshots = []
            if not snapshots:
                self._payload["options"] = {"rows": 0}
                return

            snap = snapshots[0]
            self._payload["snapshot"] = {
                "snapshot_ts": _coerce_datetime(getattr(snap, "snapshot_ts", None)),
                "expiration_date": _coerce_datetime(
                    getattr(snap, "expiration_date", None)
                ),
                "atm_strike": getattr(snap, "atm_strike", None),
                "iv_atm": getattr(snap, "iv_atm", None),
                "skew": getattr(snap, "skew", None),
                "term_structure": getattr(snap, "term_structure", None),
            }

            try:
                series_rows = (
                    session.execute(
                        select(OptionSeries)
                        .where(OptionSeries.underlying_instrument_id == instrument.id)
                        .order_by(OptionSeries.expiration_date.asc())
                        .limit(self.max_strikes)
                    )
                    .scalars()
                    .all()
                )
            except Exception:  # noqa: BLE001
                series_rows = []
            self._payload["options"] = {
                "rows": len(series_rows),
                "series": [
                    {
                        "expiration_date": _coerce_datetime(
                            getattr(row, "expiration_date", None)
                        ),
                        "strike": getattr(row, "strike", None),
                        "option_type": getattr(row, "option_type", None),
                        "open_interest": getattr(row, "open_interest", None),
                        "implied_volatility": getattr(
                            row, "implied_volatility", None
                        ),
                    }
                    for row in series_rows
                ],
            }

        self.add_provenance_source("options_chain_provider")
        self.add_lineage(
            transform_kind="data_product_load",
            target_table_id=None,
            summary=f"loaded option chain for {self.vt_symbol}",
            actor=self.product_kind,
        )


def _coerce_datetime(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


__all__ = ["OptionChainEntity"]
