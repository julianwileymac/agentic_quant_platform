"""Lightweight catalyst extractor — no LLM.

Scans a news digest and a calendar-events list for upcoming catalysts
(earnings, product launches, regulatory decisions). The output is fed
to the equity report sections so they can reference catalysts without
an extra LLM round-trip.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


_CATALYST_KEYWORDS: dict[str, list[str]] = {
    "earnings": ["earnings", "q1", "q2", "q3", "q4", "results", "guidance"],
    "product": ["launch", "release", "unveil", "ship", "rollout", "available"],
    "regulatory": [
        "fda",
        "doj",
        "ftc",
        "sec ",
        "antitrust",
        "approval",
        "ruling",
        "fine",
    ],
    "corporate_action": [
        "acquisition",
        "merger",
        "spin-off",
        "dividend",
        "buyback",
        "split",
    ],
    "macro": ["fomc", "cpi", "ppi", "rate decision", "jobs report"],
}


def _classify(text: str) -> list[str]:
    blob = text.lower()
    return [k for k, terms in _CATALYST_KEYWORDS.items() if any(t in blob for t in terms)]


def extract_catalysts(
    *,
    news: list[dict[str, Any]] | None,
    calendar_events: list[dict[str, Any]] | None = None,
    as_of: datetime | None = None,
    horizon_days: int = 30,
) -> list[dict[str, Any]]:
    """Return upcoming catalysts inferred from news + calendar_events."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    horizon_end = (as_of or datetime.utcnow()) + timedelta(days=horizon_days)
    horizon_start = (as_of or datetime.utcnow()) - timedelta(days=7)

    for item in news or []:
        title = str(item.get("title") or item.get("headline") or "")
        summary = str(item.get("summary") or item.get("description") or "")
        text = f"{title} {summary}"
        kinds = _classify(text)
        if not kinds:
            continue
        ts_raw = item.get("published_at") or item.get("publishedAt") or item.get("ts")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except Exception:
                ts = None
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = None
        for k in kinds:
            key = (k, title[:80])
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "kind": k,
                    "headline": title or "(news)",
                    "summary": summary[:200],
                    "ts": ts.isoformat() if ts else None,
                    "source": "news",
                }
            )

    for ev in calendar_events or []:
        ts_raw = ev.get("event_date") or ev.get("ts")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except Exception:
                ts = None
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = None
        if ts and not (horizon_start <= ts <= horizon_end):
            continue
        out.append(
            {
                "kind": str(ev.get("kind") or ev.get("event_type") or "calendar"),
                "headline": str(ev.get("title") or ev.get("name") or ""),
                "summary": str(ev.get("description") or ""),
                "ts": ts.isoformat() if ts else None,
                "source": "calendar",
            }
        )

    out.sort(key=lambda c: c.get("ts") or "")
    return out


def normalise_news_sentiment(news: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Aggregate naive sentiment counts. Used by the prompt builders."""
    if not news:
        return {"n": 0, "pos": 0, "neg": 0, "neut": 0}
    pos = neg = neut = 0
    for item in news:
        sent = str(item.get("sentiment") or item.get("score") or "").lower()
        if sent in ("positive", "+1", "1") or _contains(item, ["beat", "strong", "raise", "surge"]):
            pos += 1
        elif sent in ("negative", "-1") or _contains(item, ["miss", "cut", "drop", "fall"]):
            neg += 1
        else:
            neut += 1
    return {"n": len(news), "pos": pos, "neg": neg, "neut": neut}


def _contains(item: dict[str, Any], terms: list[str]) -> bool:
    blob = (
        f"{item.get('title') or item.get('headline') or ''} "
        f"{item.get('summary') or item.get('description') or ''}"
    ).lower()
    # Loose stem match — "beats" / "beat" / "missed" all count.
    return any(re.search(rf"\b{t}", blob) for t in terms)


__all__ = ["extract_catalysts", "normalise_news_sentiment"]
