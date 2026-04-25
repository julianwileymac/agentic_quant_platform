"""Portfolio analytics service.

Computes positions, P&L, allocations, exposures, and risk metrics
from the existing ``orders`` + ``fills`` execution ledger so the
Portfolio page can render live dashboards without a paper-trading
account dependency.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Iterable

import numpy as np
import pandas as pd
from sqlalchemy import select

from aqp.core.types import Symbol
from aqp.persistence.db import get_session
from aqp.persistence.models import Fill, Instrument

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fills_dataframe(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    backtest_id: str | None = None,
) -> pd.DataFrame:
    with get_session() as session:
        stmt = select(Fill).order_by(Fill.created_at)
        if start is not None:
            stmt = stmt.where(Fill.created_at >= start)
        if end is not None:
            stmt = stmt.where(Fill.created_at <= end)
        rows = session.execute(stmt).scalars().all()
        # Materialise into pure dicts inside the session so detached-instance
        # errors after commit() don't trip up the caller.
        records = [
            {
                "id": r.id,
                "vt_symbol": r.vt_symbol,
                "side": (r.side or "buy").lower(),
                "quantity": float(r.quantity or 0.0),
                "price": float(r.price or 0.0),
                "commission": float(r.commission or 0.0),
                "slippage": float(r.slippage or 0.0),
                "created_at": pd.Timestamp(r.created_at),
            }
            for r in rows
        ]
    if not records:
        return pd.DataFrame(
            columns=["id", "vt_symbol", "side", "quantity", "price", "commission", "slippage", "created_at"]
        )
    return pd.DataFrame(records)


def _instrument_meta(vt_symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
    syms = list(vt_symbols)
    if not syms:
        return {}
    try:
        with get_session() as session:
            rows = session.execute(
                select(Instrument).where(Instrument.vt_symbol.in_(syms))
            ).scalars().all()
            return {
                r.vt_symbol: {
                    "asset_class": getattr(r, "asset_class", None),
                    "sector": getattr(r, "sector", None),
                    "industry": getattr(r, "industry", None),
                    "country": getattr(r, "country", None),
                    "currency": getattr(r, "currency", None),
                    "issuer_id": getattr(r, "issuer_id", None),
                }
                for r in rows
            }
    except Exception:
        logger.info("portfolio_service: instrument lookup failed", exc_info=True)
        return {}


def _latest_close(vt_symbols: list[str]) -> dict[str, float]:
    if not vt_symbols:
        return {}
    try:
        from aqp.data.duckdb_engine import DuckDBHistoryProvider

        provider = DuckDBHistoryProvider()
        end = pd.Timestamp.utcnow()
        start = end - timedelta(days=14)
        bars = provider.get_bars(
            [Symbol.parse(s) for s in vt_symbols], start=start, end=end
        )
        if bars is None or bars.empty:
            return {}
        latest = (
            bars.sort_values("timestamp")
            .groupby("vt_symbol")
            .tail(1)[["vt_symbol", "close"]]
            .set_index("vt_symbol")["close"]
            .to_dict()
        )
        return {k: float(v) for k, v in latest.items()}
    except Exception:
        logger.info("portfolio_service: latest_close lookup failed", exc_info=True)
        return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_positions(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """Return per-symbol positions reduced from the fills ledger."""
    fills = _fills_dataframe(start=start, end=end)
    if fills.empty:
        return {"positions": [], "n_symbols": 0}
    fills = fills.copy()
    fills["signed_qty"] = fills.apply(
        lambda r: float(r["quantity"]) if r["side"] == "buy" else -float(r["quantity"]),
        axis=1,
    )
    fills["notional"] = fills["signed_qty"] * fills["price"]
    grouped = fills.groupby("vt_symbol").agg(
        qty=("signed_qty", "sum"),
        net_cost=("notional", "sum"),
        fees=("commission", "sum"),
        slippage_total=("slippage", "sum"),
    ).reset_index()
    grouped = grouped[grouped["qty"].abs() > 1e-9]
    if grouped.empty:
        return {"positions": [], "n_symbols": 0}
    avg_cost = (grouped["net_cost"] / grouped["qty"]).abs()
    grouped["avg_cost"] = avg_cost.where(grouped["qty"] != 0, 0.0)
    last = _latest_close(list(grouped["vt_symbol"]))
    grouped["last_price"] = grouped["vt_symbol"].map(lambda s: last.get(s, 0.0))
    grouped["market_value"] = grouped["qty"] * grouped["last_price"]
    grouped["unrealized_pnl"] = grouped["market_value"] - grouped["net_cost"]
    meta = _instrument_meta(list(grouped["vt_symbol"]))
    rows: list[dict[str, Any]] = []
    for _, r in grouped.iterrows():
        m = meta.get(r["vt_symbol"], {})
        rows.append(
            {
                "vt_symbol": r["vt_symbol"],
                "qty": float(r["qty"]),
                "avg_cost": float(r["avg_cost"]),
                "last_price": float(r["last_price"]),
                "market_value": float(r["market_value"]),
                "unrealized_pnl": float(r["unrealized_pnl"]),
                "fees": float(r["fees"]),
                "slippage": float(r["slippage_total"]),
                "asset_class": m.get("asset_class"),
                "sector": m.get("sector"),
                "industry": m.get("industry"),
                "country": m.get("country"),
                "currency": m.get("currency"),
                "issuer_id": m.get("issuer_id"),
            }
        )
    return {"positions": rows, "n_symbols": len(rows)}


def compute_pnl_series(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    initial_cash: float = 0.0,
) -> dict[str, Any]:
    """Return daily realised P&L + cumulative equity from the fills ledger.

    Mark-to-market uses the daily close from DuckDB. Positions are
    reduced day-by-day so the curve reflects intra-day fills.
    """
    fills = _fills_dataframe(start=start, end=end)
    if fills.empty:
        return {"index": [], "equity": [], "daily_pnl": []}
    fills = fills.sort_values("created_at").copy()
    # Strip timezone info so subsequent timestamp comparisons stay consistent.
    if pd.api.types.is_datetime64_any_dtype(fills["created_at"]):
        try:
            fills["created_at"] = fills["created_at"].dt.tz_localize(None)
        except (TypeError, AttributeError):
            pass
    fills["day"] = fills["created_at"].dt.normalize()
    fills["signed_qty"] = fills.apply(
        lambda r: float(r["quantity"]) if r["side"] == "buy" else -float(r["quantity"]),
        axis=1,
    )
    fills["cash_flow"] = -fills["signed_qty"] * fills["price"] - fills["commission"]
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    days = pd.bdate_range(fills["day"].min(), max(fills["day"].max(), today))
    cash = float(initial_cash)
    positions: dict[str, dict[str, float]] = {}
    out_index: list[str] = []
    out_equity: list[float] = []
    out_daily: list[float] = []
    syms = list(fills["vt_symbol"].unique())
    # Pull a daily close panel covering the full window once.
    try:
        from aqp.data.duckdb_engine import DuckDBHistoryProvider

        provider = DuckDBHistoryProvider()
        bars = provider.get_bars(
            [Symbol.parse(s) for s in syms],
            start=days[0],
            end=days[-1] + timedelta(days=1),
        )
        bars = bars.sort_values(["vt_symbol", "timestamp"]) if not bars.empty else bars
    except Exception:
        bars = pd.DataFrame()
    bars_by_day: dict[tuple[pd.Timestamp, str], float] = {}
    if not bars.empty:
        for _, row in bars.iterrows():
            bars_by_day[(pd.Timestamp(row["timestamp"]).normalize(), row["vt_symbol"])] = float(
                row["close"]
            )
    prev_equity: float | None = None
    for d in days:
        day_fills = fills[fills["day"] == d]
        for _, r in day_fills.iterrows():
            sym = r["vt_symbol"]
            slot = positions.setdefault(sym, {"qty": 0.0, "cost": 0.0})
            new_qty = slot["qty"] + r["signed_qty"]
            slot["cost"] += r["signed_qty"] * r["price"]
            slot["qty"] = new_qty
            cash += r["cash_flow"]
        market_value = 0.0
        for sym, slot in positions.items():
            close = bars_by_day.get((d, sym))
            if close is None:
                continue
            market_value += slot["qty"] * close
        equity = cash + market_value
        daily = 0.0 if prev_equity is None else equity - prev_equity
        prev_equity = equity
        out_index.append(d.isoformat())
        out_equity.append(float(equity))
        out_daily.append(float(daily))
    return {"index": out_index, "equity": out_equity, "daily_pnl": out_daily}


def compute_allocations(
    *,
    by: str = "sector",
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    pos = compute_positions(start=start, end=end).get("positions", [])
    if not pos:
        return {"by": by, "buckets": []}
    df = pd.DataFrame(pos)
    if by not in {"sector", "industry", "asset_class", "country", "currency"}:
        by = "sector"
    df[by] = df[by].fillna("unknown")
    df["abs_value"] = df["market_value"].abs()
    grouped = df.groupby(by)["abs_value"].sum().reset_index()
    total = float(grouped["abs_value"].sum()) or 1.0
    grouped["weight"] = grouped["abs_value"] / total
    grouped = grouped.sort_values("abs_value", ascending=False)
    return {
        "by": by,
        "buckets": [
            {
                "name": str(r[by]),
                "value": float(r["abs_value"]),
                "weight": float(r["weight"]),
            }
            for _, r in grouped.iterrows()
        ],
    }


def compute_exposures(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    pos = compute_positions(start=start, end=end).get("positions", [])
    if not pos:
        return {
            "long_exposure": 0.0,
            "short_exposure": 0.0,
            "gross_exposure": 0.0,
            "net_exposure": 0.0,
            "n_long": 0,
            "n_short": 0,
        }
    long_v = sum(float(p["market_value"]) for p in pos if p["market_value"] > 0)
    short_v = sum(float(p["market_value"]) for p in pos if p["market_value"] < 0)
    return {
        "long_exposure": float(long_v),
        "short_exposure": float(short_v),
        "gross_exposure": float(long_v - short_v),
        "net_exposure": float(long_v + short_v),
        "n_long": int(sum(1 for p in pos if p["market_value"] > 0)),
        "n_short": int(sum(1 for p in pos if p["market_value"] < 0)),
    }


def compute_risk(
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    initial_cash: float = 0.0,
    benchmark_vt_symbol: str | None = None,
) -> dict[str, Any]:
    series = compute_pnl_series(start=start, end=end, initial_cash=initial_cash)
    equity = pd.Series(series["equity"], index=pd.to_datetime(series["index"]), dtype=float)
    if equity.empty or len(equity) < 2:
        return {
            "sharpe": None,
            "max_drawdown": None,
            "var_95": None,
            "cvar_95": None,
            "ann_vol": None,
            "ann_return": None,
            "beta": None,
        }
    returns = equity.pct_change().fillna(0.0)
    ann_factor = 252.0
    ann_return = float((1.0 + returns.mean()) ** ann_factor - 1.0)
    ann_vol = float(returns.std() * np.sqrt(ann_factor))
    sharpe = float(returns.mean() / returns.std() * np.sqrt(ann_factor)) if returns.std() else None
    cummax = equity.cummax()
    dd = (equity - cummax) / cummax
    max_dd = float(dd.min())
    var_95 = float(returns.quantile(0.05))
    cvar_95 = float(returns[returns <= var_95].mean()) if (returns <= var_95).any() else float("nan")
    beta: float | None = None
    if benchmark_vt_symbol:
        try:
            from aqp.data.duckdb_engine import DuckDBHistoryProvider

            provider = DuckDBHistoryProvider()
            bars = provider.get_bars(
                [Symbol.parse(benchmark_vt_symbol)],
                start=pd.Timestamp(equity.index.min()),
                end=pd.Timestamp(equity.index.max()),
            )
            if not bars.empty:
                bench = (
                    bars.sort_values("timestamp")
                    .set_index(pd.to_datetime(bars["timestamp"]))["close"]
                    .pct_change()
                    .reindex(returns.index)
                    .fillna(0.0)
                )
                if bench.std() > 0:
                    cov = float(np.cov(returns, bench, ddof=0)[0, 1])
                    beta = float(cov / (bench.var() if bench.var() else 1.0))
        except Exception:
            logger.info("portfolio_service: beta calc failed", exc_info=True)
    return {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "var_95": var_95,
        "cvar_95": cvar_95,
        "ann_vol": ann_vol,
        "ann_return": ann_return,
        "beta": beta,
    }


__all__ = [
    "compute_allocations",
    "compute_exposures",
    "compute_pnl_series",
    "compute_positions",
    "compute_risk",
]
