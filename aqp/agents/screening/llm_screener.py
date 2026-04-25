"""LLM-driven universe selector / stock screener.

Takes a candidate universe + a compact snapshot (fundamentals, recent
sentiment, technicals) and returns a shortlist ranked by the LLM's
conviction. Two surfaces:

- :class:`LLMScreener` — pure callable, returns ``list[dict]``.
- :class:`LLMScreenerAlpha` — an ``IAlphaModel`` wrapping the screener
  that emits :class:`aqp.core.types.Signal` objects ready for portfolio
  construction.
- :class:`LLMUniverseSelector` — also implements
  :class:`IUniverseSelectionModel` so the screener can drive stage 1 of
  the Lean-style pipeline.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.agents.financial.base import extract_json
from aqp.core.interfaces import IAlphaModel, IUniverseSelectionModel
from aqp.core.registry import agent, universe
from aqp.core.types import Direction, Signal, Symbol
from aqp.llm.ollama_client import complete

logger = logging.getLogger(__name__)


_SCREENER_SYSTEM = """\
You are an equity screener. Given a list of candidate tickers with a
structured snapshot of recent fundamentals, technicals, and sentiment,
rank the top ``k`` names by conviction.

Respond ONLY with JSON:
  shortlist: [{
    ticker: string,
    rank: int,
    direction: "LONG" | "SHORT" | "NEUTRAL",
    conviction: number (0..1),
    rationale: string,
    key_risks: [string]
  }]

Rules:
- Prefer names with confluence across fundamentals, sentiment, and
  technicals.
- Never choose more than ``k`` names.
- Leave out names with insufficient data.
"""


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return dict(value or {})
    except Exception:
        return {}


def _managed_snapshot_map(universe: list[Symbol]) -> dict[str, dict[str, Any]]:
    vt_symbols = [s.vt_symbol for s in universe]
    if not vt_symbols:
        return {}
    try:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import Instrument
    except Exception:
        return {}

    try:
        with get_session() as session:
            rows = session.execute(
                select(Instrument).where(Instrument.vt_symbol.in_(vt_symbols))
            ).scalars().all()
    except Exception:
        logger.info("managed snapshot lookup failed", exc_info=True)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        meta = _as_dict(row.meta)
        av_meta = _as_dict(meta.get("alpha_vantage"))
        out[row.ticker.upper()] = {
            "exchange": row.exchange,
            "asset_class": row.asset_class,
            "security_type": row.security_type,
            "sector": row.sector,
            "industry": row.industry,
            "country": row.country,
            "currency": row.currency,
            "listing_status": av_meta.get("status"),
            "universe_source": "managed_snapshot",
        }
    return out


@agent("LLMScreener", tags=("llm", "screener", "universe"))
class LLMScreener:
    """Compact LLM ranker over a structured candidate universe."""

    def __init__(
        self,
        k: int = 10,
        provider: str | None = None,
        model: str | None = None,
        tier: str = "deep",
        min_conviction: float = 0.5,
    ) -> None:
        self.k = int(k)
        self.provider = provider
        self.model = model
        self.tier = tier
        self.min_conviction = float(min_conviction)

    def rank(
        self,
        snapshots: list[dict[str, Any]],
        as_of: str | datetime | None = None,
    ) -> list[dict[str, Any]]:
        if not snapshots:
            return []
        as_of_str = (
            as_of.date().isoformat() if isinstance(as_of, datetime) else str(as_of or "")
        )
        user = (
            f"as_of: {as_of_str}\n"
            f"k: {self.k}\n"
            f"candidates:\n{json.dumps(snapshots[:60], default=str)[:14000]}\n"
        )
        try:
            result = complete(
                tier=self.tier,
                messages=[
                    {"role": "system", "content": _SCREENER_SYSTEM},
                    {"role": "user", "content": user},
                ],
                provider=self.provider,
                model=self.model,
            )
        except Exception:
            logger.exception("LLMScreener complete failed")
            return []
        payload = extract_json(result.content)
        shortlist = payload.get("shortlist", []) or []
        cleaned: list[dict[str, Any]] = []
        for row in shortlist:
            if row.get("conviction", 0.0) < self.min_conviction:
                continue
            cleaned.append(
                {
                    "ticker": str(row.get("ticker", "")).upper(),
                    "rank": int(row.get("rank", 0) or 0),
                    "direction": str(row.get("direction", "LONG")).upper(),
                    "conviction": float(row.get("conviction", 0.5) or 0.5),
                    "rationale": str(row.get("rationale", "")),
                    "key_risks": list(row.get("key_risks", []) or []),
                }
            )
        cleaned.sort(key=lambda r: r["rank"] or 999)
        return cleaned[: self.k]


@agent("LLMScreenerAlpha", tags=("llm", "screener", "alpha"))
class LLMScreenerAlpha(IAlphaModel):
    """Alpha adapter — emit one :class:`Signal` per shortlisted ticker."""

    def __init__(
        self,
        snapshot_fn: Any = None,
        k: int = 10,
        provider: str | None = None,
        model: str | None = None,
        tier: str = "deep",
        min_conviction: float = 0.5,
        strength: float = 0.15,
    ) -> None:
        self.snapshot_fn = snapshot_fn
        self.screener = LLMScreener(
            k=k, provider=provider, model=model, tier=tier, min_conviction=min_conviction
        )
        self.strength = float(strength)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        snapshots = self._build_snapshots(universe, bars, context)
        ranked = self.screener.rank(snapshots, as_of=context.get("current_time"))
        out: list[Signal] = []
        for row in ranked:
            sym = next(
                (s for s in universe if s.ticker.upper() == row["ticker"]), None
            )
            if sym is None:
                continue
            direction = (
                Direction.LONG if row["direction"] == "LONG" else Direction.SHORT
            )
            out.append(
                Signal(
                    symbol=sym,
                    strength=self.strength * row["conviction"],
                    direction=direction,
                    timestamp=context.get("current_time") or datetime.utcnow(),
                    confidence=row["conviction"],
                    horizon_days=5,
                    source=f"LLMScreener({row['rank']})",
                    rationale=row["rationale"],
                )
            )
        return out

    def _build_snapshots(
        self,
        universe: list[Symbol],
        bars: pd.DataFrame,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self.snapshot_fn is not None:
            try:
                return list(self.snapshot_fn(universe, bars, context))
            except Exception:
                logger.exception("custom snapshot_fn failed")

        # Default snapshot — quick summary from recent bars, optionally enriched
        # with managed snapshot metadata + fundamentals.
        frame = bars if isinstance(bars, pd.DataFrame) else pd.DataFrame()
        managed = _managed_snapshot_map(universe)
        fundamentals_map = _as_dict(context.get("fundamentals_map"))
        enrich_fundamentals = bool(context.get("screener_include_fundamentals", True))
        max_fundamentals = max(0, int(context.get("screener_fundamentals_limit", 12) or 0))
        if enrich_fundamentals and not fundamentals_map and max_fundamentals > 0:
            try:
                from aqp.agents.tools.fundamentals_tool import compute_fundamentals_snapshot

                for sym in universe[:max_fundamentals]:
                    snapshot = compute_fundamentals_snapshot(sym.vt_symbol, context.get("current_time"))
                    if snapshot:
                        fundamentals_map[sym.ticker.upper()] = snapshot
            except Exception:
                logger.info("screener fundamentals enrichment unavailable", exc_info=True)

        snapshots: list[dict[str, Any]] = []
        for sym in universe:
            sub = (
                frame[frame["vt_symbol"] == sym.vt_symbol].tail(30)
                if not frame.empty
                else frame
            )
            snapshot: dict[str, Any] = {"ticker": sym.ticker}
            meta = _as_dict(managed.get(sym.ticker.upper()))
            if meta:
                snapshot.update({k: v for k, v in meta.items() if v not in (None, "")})

            extra_fundamentals = _as_dict(fundamentals_map.get(sym.ticker.upper()))
            if extra_fundamentals:
                snapshot.update(
                    {
                        "trailing_pe": extra_fundamentals.get("trailingPE"),
                        "forward_pe": extra_fundamentals.get("forwardPE"),
                        "revenue_growth": extra_fundamentals.get("revenueGrowth"),
                        "earnings_growth": extra_fundamentals.get("earningsGrowth"),
                        "profit_margin": extra_fundamentals.get("profitMargins"),
                        "operating_margin": extra_fundamentals.get("operatingMargins"),
                        "market_cap": extra_fundamentals.get("marketCap"),
                    }
                )

            if sub.empty:
                snapshot["note"] = "no-data"
                snapshots.append(snapshot)
                continue
            try:
                ret_5 = float(sub["close"].pct_change(5).iloc[-1])
                ret_20 = float(sub["close"].pct_change(20).iloc[-1])
                vol = float(sub["close"].pct_change().std())
            except Exception:
                ret_5 = ret_20 = vol = 0.0
            snapshot.update(
                {
                    "ret_5d": round(ret_5, 4),
                    "ret_20d": round(ret_20, 4),
                    "vol": round(vol, 4),
                }
            )
            snapshots.append(snapshot)
        return snapshots


@universe("LLMUniverseSelector", tags=("llm", "universe"))
class LLMUniverseSelector(IUniverseSelectionModel):
    """Stage-1 universe selector that picks a shortlist every rebalance."""

    def __init__(
        self,
        base_universe: list[Symbol] | None = None,
        k: int = 10,
        provider: str | None = None,
        model: str | None = None,
        tier: str = "deep",
    ) -> None:
        self.base_universe = list(base_universe or [])
        self.alpha = LLMScreenerAlpha(
            k=k, provider=provider, model=model, tier=tier, min_conviction=0.5
        )

    def select(self, timestamp: datetime, context: dict[str, Any]) -> list[Symbol]:
        base = context.get("base_universe", self.base_universe)
        bars = context.get("history", pd.DataFrame())
        signals = self.alpha.generate_signals(
            bars=bars,
            universe=list(base),
            context={**context, "current_time": timestamp},
        )
        return [s.symbol for s in signals]


__all__ = ["LLMScreener", "LLMScreenerAlpha", "LLMUniverseSelector"]
