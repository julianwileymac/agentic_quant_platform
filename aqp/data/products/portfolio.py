"""Portfolio entity-centric data product."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select

from aqp.data.products.base import BaseDataProduct
from aqp.persistence.db import get_session
from aqp.persistence.models import Fill, LedgerEntry, OrderRecord

logger = logging.getLogger(__name__)


class PortfolioEntity(BaseDataProduct):
    """Read-only view of one portfolio's positions, exposures, and recent fills.

    ``portfolio_id`` is the strategy / session / paper-trading id that
    owns the orders and fills (depending on the schema). Falls back to
    a free-form ``key`` so callers can identify by either id or the
    domain-specific tag stored in ``LedgerEntry.tags``.
    """

    product_kind = "portfolio"

    def __init__(
        self,
        portfolio_id: str,
        *,
        as_of: datetime | None = None,
        recent_fills: int = 10,
    ) -> None:
        super().__init__(entity_id=portfolio_id, as_of=as_of)
        self.portfolio_id = str(portfolio_id)
        self.recent_fills = max(int(recent_fills), 1)

    def load(self) -> None:
        with get_session() as session:
            self._payload["positions"] = self._lookup_positions(session)
            self._payload["fills"] = self._lookup_recent_fills(session)
            self._payload["risk"] = self._lookup_risk(session)
        self.add_lineage(
            transform_kind="data_product_load",
            target_table_id=None,
            summary=f"loaded portfolio entity for {self.portfolio_id}",
            actor=self.product_kind,
        )

    # ------------------------------------------------------------------
    # ORM helpers
    # ------------------------------------------------------------------

    def _lookup_positions(self, session) -> list[dict[str, Any]]:
        try:
            stmt = (
                select(
                    Fill.vt_symbol,
                    func.sum(Fill.qty).label("net_qty"),
                    func.avg(Fill.price).label("avg_price"),
                )
                .where(self._portfolio_filter(Fill))
                .group_by(Fill.vt_symbol)
            )
            rows = session.execute(stmt).all()
        except Exception:  # noqa: BLE001
            return []
        return [
            {
                "vt_symbol": row.vt_symbol,
                "net_qty": float(row.net_qty) if row.net_qty is not None else 0.0,
                "avg_price": float(row.avg_price) if row.avg_price is not None else None,
            }
            for row in rows
        ]

    def _lookup_recent_fills(self, session) -> list[dict[str, Any]]:
        try:
            stmt = (
                select(Fill)
                .where(self._portfolio_filter(Fill))
                .order_by(desc(Fill.ts))
                .limit(self.recent_fills)
            )
            rows = session.execute(stmt).scalars().all()
        except Exception:  # noqa: BLE001
            return []
        return [
            {
                "vt_symbol": row.vt_symbol,
                "ts": row.ts.isoformat() if row.ts else None,
                "side": row.side,
                "qty": float(row.qty) if row.qty is not None else None,
                "price": float(row.price) if row.price is not None else None,
                "fees": float(row.fees) if row.fees is not None else None,
            }
            for row in rows
        ]

    def _lookup_risk(self, session) -> dict[str, Any]:
        try:
            stmt = (
                select(LedgerEntry)
                .where(self._portfolio_filter(LedgerEntry))
                .order_by(desc(LedgerEntry.ts))
                .limit(1)
            )
            latest = session.execute(stmt).scalars().first()
            if latest is None:
                return {}
            return {
                "ts": latest.ts.isoformat() if latest.ts else None,
                "equity": float(latest.equity) if getattr(latest, "equity", None) is not None else None,
                "cash": float(latest.cash) if getattr(latest, "cash", None) is not None else None,
                "drawdown": float(latest.drawdown)
                if getattr(latest, "drawdown", None) is not None
                else None,
                "daily_pnl": float(latest.daily_pnl)
                if getattr(latest, "daily_pnl", None) is not None
                else None,
            }
        except Exception:  # noqa: BLE001
            return {}

    def _portfolio_filter(self, model: Any) -> Any:
        # Try common fields in order. ORM rows expose .strategy_id /
        # .backtest_run_id / .session_id depending on the schema.
        for attr in ("strategy_id", "backtest_run_id", "session_id", "tag"):
            column = getattr(model, attr, None)
            if column is not None:
                return column == self.portfolio_id
        # Final fallback — id always exists on every row.
        return getattr(model, "id") == self.portfolio_id


__all__ = ["PortfolioEntity"]
