"""FinGPT-Forecaster — LLM-powered directional forecaster."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from aqp.ml.applications.forecaster.prompts import (
    FORECASTER_SYSTEM,
    FORECASTER_USER_TMPL,
)

logger = logging.getLogger(__name__)


_DIRECTION_TO_NUM = {"up": 1, "down": -1, "flat": 0}


@dataclass
class ForecasterOutput:
    direction: str
    direction_num: int
    confidence: float
    horizon_days: int
    rationale: str
    risks: list[str]
    token_cost_usd: float
    provider: str
    model: str


class FinGPTForecaster:
    """One-shot directional forecaster that calls any provider LLM.

    Parameters
    ----------
    provider / model:
        Optional overrides for the LLM tier (otherwise the deep tier from
        :mod:`aqp.llm.providers` is used).
    n_past_weeks:
        How many weeks of news to pull per call. Matches FinGPT-Forecaster's
        original UI slider.
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        n_past_weeks: int = 2,
    ) -> None:
        self.provider = provider
        self.model = model
        self.n_past_weeks = int(n_past_weeks)

    def forecast(
        self,
        ticker: str,
        as_of: datetime | str,
        news_items: list[dict[str, Any]] | None = None,
        fundamentals: dict[str, Any] | None = None,
    ) -> ForecasterOutput:
        """Run one forecaster call.

        Missing ``news_items`` / ``fundamentals`` are gathered lazily from
        the built-in tools; the caller can pass pre-computed payloads to
        save on network round-trips during bulk runs.
        """
        from aqp.llm.ollama_client import complete

        as_of_dt = (
            as_of if isinstance(as_of, datetime)
            else datetime.fromisoformat(str(as_of))
        )

        if fundamentals is None:
            try:
                from aqp.agents.tools.fundamentals_tool import compute_fundamentals_snapshot

                fundamentals = compute_fundamentals_snapshot(ticker, as_of_dt) or {}
            except Exception:
                fundamentals = {}

        if news_items is None:
            try:
                from aqp.agents.tools.news_tool import fetch_news_items, score_items

                items = fetch_news_items(
                    ticker,
                    as_of=as_of_dt,
                    lookback_days=self.n_past_weeks * 7,
                )
                news_items = score_items(items) if items else []
            except Exception:
                news_items = []

        user = FORECASTER_USER_TMPL.format(
            ticker=ticker,
            as_of=as_of_dt.date().isoformat(),
            n_past_weeks=self.n_past_weeks,
            fundamentals=json.dumps(fundamentals, default=str)[:4000],
            headlines=json.dumps(news_items[:20], default=str)[:4000],
        )

        result = complete(
            tier="deep",
            messages=[
                {"role": "system", "content": FORECASTER_SYSTEM},
                {"role": "user", "content": user},
            ],
            provider=self.provider,
            model=self.model,
        )
        payload = _parse_json(result.content)
        direction = str(payload.get("direction", "flat")).lower()
        direction_num = _DIRECTION_TO_NUM.get(direction, 0)

        return ForecasterOutput(
            direction=direction,
            direction_num=direction_num,
            confidence=float(payload.get("confidence", 0.5) or 0.5),
            horizon_days=int(payload.get("horizon_days", 5) or 5),
            rationale=str(payload.get("rationale", "") or ""),
            risks=list(payload.get("risks", []) or []),
            token_cost_usd=float(result.cost_usd),
            provider=result.provider,
            model=result.model,
        )


# ---------------------------------------------------------------------------
# Parsing helpers (tolerant to code fences + single quotes)
# ---------------------------------------------------------------------------


import re  # noqa: E402

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    s = text.strip()
    m = _JSON_FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()
    if not s.startswith("{"):
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start : end + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        try:
            return json.loads(s.replace("'", '"'))
        except json.JSONDecodeError:
            logger.debug("forecaster JSON parse failed: %s", text[:120])
            return {}


def default_forecast_window(as_of: datetime, days: int = 7) -> tuple[datetime, datetime]:
    """Convenience for callers that want the [as_of, as_of+days] range."""
    return as_of, as_of + timedelta(days=days)
