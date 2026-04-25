"""Walk-Forward Optimization — rolling train/test windows."""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import pandas as pd

from aqp.backtest.runner import run_backtest_from_config

logger = logging.getLogger(__name__)


def run_walk_forward(
    cfg: dict[str, Any],
    train_window_days: int = 252,
    test_window_days: int = 63,
    step_days: int = 63,
    run_name: str = "wfo",
) -> dict[str, Any]:
    """Run the backtest over rolling (train, test) windows, collecting OOS metrics."""
    bt_cfg = cfg.get("backtest", {}).get("kwargs", {})
    start = pd.Timestamp(bt_cfg.get("start") or "2020-01-01")
    end = pd.Timestamp(bt_cfg.get("end") or pd.Timestamp.today())

    windows = []
    cursor = start + pd.Timedelta(days=train_window_days)
    while cursor + pd.Timedelta(days=test_window_days) <= end:
        train_start = cursor - pd.Timedelta(days=train_window_days)
        train_end = cursor
        test_start = cursor
        test_end = cursor + pd.Timedelta(days=test_window_days)
        windows.append((train_start, train_end, test_start, test_end))
        cursor = cursor + pd.Timedelta(days=step_days)

    results = []
    for i, (ts, te, vs, ve) in enumerate(windows):
        window_cfg = deepcopy(cfg)
        window_cfg.setdefault("backtest", {}).setdefault("kwargs", {}).update(
            {"start": str(vs.date()), "end": str(ve.date())}
        )
        logger.info(
            "[WFO %d/%d] train=%s..%s test=%s..%s", i + 1, len(windows), ts.date(), te.date(), vs.date(), ve.date()
        )
        try:
            r = run_backtest_from_config(
                window_cfg, run_name=f"{run_name}-w{i}", persist=False
            )
            results.append(
                {
                    "window": i,
                    "train_start": str(ts.date()),
                    "train_end": str(te.date()),
                    "test_start": str(vs.date()),
                    "test_end": str(ve.date()),
                    "sharpe": r["sharpe"],
                    "sortino": r["sortino"],
                    "max_drawdown": r["max_drawdown"],
                    "total_return": r["total_return"],
                }
            )
        except Exception as e:  # pragma: no cover
            logger.exception("Window %d failed", i)
            results.append({"window": i, "error": str(e)})

    oos_sharpes = [r["sharpe"] for r in results if "sharpe" in r]
    return {
        "n_windows": len(results),
        "mean_oos_sharpe": sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0.0,
        "windows": results,
    }
