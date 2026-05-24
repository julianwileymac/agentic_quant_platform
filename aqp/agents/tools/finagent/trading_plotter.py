"""``TradingPlotterTool`` — summarise per-step trading actions + PnL."""
from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


try:
    from crewai.tools import BaseTool  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001

    class BaseTool:  # type: ignore[no-redef]
        name: str = "tool"
        description: str = ""

        def _run(self, *args: Any, **kwargs: Any) -> str:
            raise NotImplementedError


class TradingPlotterTool(BaseTool):
    """Summarise a list of per-step action+PnL records into a text block."""

    name: str = "trading_plotter"
    description: str = (
        "Summarise per-step trading actions + PnL into a compact text "
        "block (count of SELL/HOLD/BUY, cumulative PnL, max drawdown, "
        "biggest win, biggest loss). Input: JSON list of "
        "{action, pnl} dicts."
    )

    def _run(self, history: list[dict[str, Any]] | str) -> str:
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except json.JSONDecodeError:
                return "input is not a JSON list"
        if not isinstance(history, list) or not history:
            return "no history provided"
        pnls = np.asarray(
            [float(h.get("pnl", 0.0) or 0.0) for h in history], dtype=np.float64
        )
        actions = [str(h.get("action", "HOLD")).upper() for h in history]
        action_counts = {a: actions.count(a) for a in ("SELL", "HOLD", "BUY")}
        cum_pnl = float(pnls.sum())
        max_win = float(pnls.max()) if pnls.size > 0 else 0.0
        max_loss = float(pnls.min()) if pnls.size > 0 else 0.0
        equity = np.cumsum(pnls)
        peak = np.maximum.accumulate(equity)
        max_dd = float((equity - peak).min()) if equity.size > 0 else 0.0
        return (
            f"steps={len(history)}; "
            f"actions={action_counts}; "
            f"cumulative_pnl={cum_pnl:.4f}; "
            f"max_win={max_win:.4f}; "
            f"max_loss={max_loss:.4f}; "
            f"max_drawdown={max_dd:.4f}"
        )


__all__ = ["TradingPlotterTool"]
