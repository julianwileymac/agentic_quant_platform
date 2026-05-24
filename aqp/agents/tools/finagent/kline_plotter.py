"""``KlinePlotterTool`` — produce a candlestick/line summary string.

Lightweight tool the FinAgent layered cascade calls during the
*low_intelligence* stage to convert a price-bar history into a
compact textual summary the LLM can reason over (low / median / high
+ trend slope + dominant pattern).

The tool intentionally returns a *string* (not an image) because the
LLM consumes text. A future enhancement may emit an actual PNG via
matplotlib + base64-encoded inline image attached to the prompt.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


try:
    from crewai.tools import BaseTool  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    # Lightweight fallback so the module imports without crewai.
    class BaseTool:  # type: ignore[no-redef]
        name: str = "tool"
        description: str = ""

        def _run(self, *args: Any, **kwargs: Any) -> str:
            raise NotImplementedError


class KlinePlotterTool(BaseTool):
    """Summarise a list of price bars into an LLM-friendly text block."""

    name: str = "kline_plotter"
    description: str = (
        "Summarise a list of OHLC price bars into a compact text block "
        "(min/max/mean, trend slope, dominant move direction). Input: "
        "a JSON list of {open, high, low, close} dicts."
    )

    def _run(self, bars: list[dict[str, float]] | str) -> str:
        if isinstance(bars, str):
            try:
                bars = json.loads(bars)
            except json.JSONDecodeError:
                return "input is not a JSON list of bars"
        if not isinstance(bars, list) or not bars:
            return "no bars provided"
        closes = np.asarray([float(b.get("close", b.get("c", 0.0))) for b in bars])
        if closes.size == 0:
            return "no close prices found"
        slope = float((closes[-1] - closes[0]) / max(len(closes) - 1, 1))
        ret_pct = float((closes[-1] - closes[0]) / max(abs(closes[0]), 1e-9))
        return (
            f"bars={len(bars)}; first={closes[0]:.4f}; last={closes[-1]:.4f}; "
            f"min={closes.min():.4f}; max={closes.max():.4f}; "
            f"mean={closes.mean():.4f}; slope_per_bar={slope:.6f}; "
            f"total_return={ret_pct:.4f}"
        )


__all__ = ["KlinePlotterTool"]
