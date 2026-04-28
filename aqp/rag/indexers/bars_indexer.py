"""Index per-symbol price/volume *summaries* into the L1 ``price_volume`` corpus.

We do **not** embed every bar — that's huge and not useful for LLMs.
Instead, for each symbol we compute a short summary card (date range,
volatility, return, average volume, recent trend) and index that.
"""
from __future__ import annotations

import logging
import statistics
from collections.abc import Iterable

from aqp.config import settings
from aqp.rag.chunker import Chunk
from aqp.rag.hierarchy import HierarchicalRAG, get_default_rag

logger = logging.getLogger(__name__)


def _summary_card(vt_symbol: str, bars: list[dict]) -> str:
    if not bars:
        return ""
    closes = [float(b.get("close", 0.0)) for b in bars if b.get("close") is not None]
    vols = [float(b.get("volume", 0.0)) for b in bars if b.get("volume") is not None]
    if len(closes) < 2:
        return ""
    pct = (closes[-1] / closes[0] - 1.0) * 100.0
    rets = [
        (closes[i] / closes[i - 1] - 1.0) for i in range(1, len(closes))
    ]
    vol = statistics.pstdev(rets) * (252**0.5) * 100.0 if rets else 0.0
    avg_vol = statistics.fmean(vols) if vols else 0.0
    first = bars[0].get("timestamp") or bars[0].get("date") or ""
    last = bars[-1].get("timestamp") or bars[-1].get("date") or ""
    return (
        f"Symbol={vt_symbol}. Window {first} .. {last}. "
        f"Close moved from {closes[0]:.4f} to {closes[-1]:.4f} ({pct:+.2f}%). "
        f"Annualised volatility {vol:.2f}%. Average daily volume {avg_vol:,.0f}."
    )


def index_bars_summary(
    *,
    symbols: Iterable[str] | None = None,
    rag: HierarchicalRAG | None = None,
    lookback_days: int = 252,
) -> int:
    """For each symbol in ``symbols``, write one summary card into L1 bars_daily."""
    rag = rag or get_default_rag()
    items: list[tuple[Chunk, dict]] = []
    syms = list(symbols) if symbols is not None else settings.universe_list
    try:
        from aqp.data.bars import get_bars
    except Exception:  # pragma: no cover
        logger.warning("aqp.data.bars unavailable; cannot summarise bars.")
        return 0
    for sym in syms:
        try:
            df = get_bars(sym, lookback_days=lookback_days)
        except Exception:  # noqa: BLE001
            logger.debug("Bars fetch failed for %s", sym, exc_info=True)
            continue
        if df is None or df.empty:
            continue
        bars = df.tail(lookback_days).to_dict(orient="records")
        text = _summary_card(sym, bars)
        if not text:
            continue
        items.append(
            (
                Chunk(text=text, index=0, token_count=len(text.split())),
                {
                    "doc_id": f"bars_daily:{sym}",
                    "vt_symbol": sym,
                    "as_of": str(bars[-1].get("timestamp", "")),
                    "source_id": f"bars_daily:{sym}",
                },
            )
        )
    return rag.index_chunks("bars_daily", items, level="l1")


__all__ = ["index_bars_summary"]
