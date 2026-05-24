"""``strategy.vbt_portfolio`` — wraps :class:`VectorbtProEngine`.

Routes through the existing vbt-pro engine in
:mod:`aqp.backtest.vbtpro.engine`. When vbt-pro isn't installed the
executor degrades to a clean error rather than crashing; the OSS
``vectorbt`` engine path remains available through the legacy
``aqp/backtest/runner.py`` shortcut for the future Phase 2 fallback.

Params:

- ``mode`` (str, default ``"signals"``) — vbt-pro mode (``signals`` /
  ``orders`` / ``holding`` / ``random``).
- ``init_cash`` (float, default 100000).
- ``fees`` (float, default 0.001).
- ``slippage`` (float, default 0.0).
- ``signal_columns`` (list[str]) — entry / exit / size columns when
  ``mode='signals'``.
"""
from __future__ import annotations

from typing import Any

from aqp.lab.executors._helpers import resolve_upstream_frame
from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    mode = str(params.get("mode") or "signals").lower()
    init_cash = float(params.get("init_cash") or 100_000.0)
    fees = float(params.get("fees") or 0.001)

    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(
            status="error",
            error="strategy.vbt_portfolio needs an upstream OHLCV / signals frame",
        )
    if "close" not in df.columns:
        return NodeResult(
            status="error",
            error="strategy.vbt_portfolio requires a 'close' column on the upstream frame",
        )

    # vbt-pro is a heavy import + licensed dep — guard so the executor
    # stays importable in dev environments without it.
    try:
        import vectorbtpro as vbt  # type: ignore[import-not-found]
    except Exception:
        try:
            import vectorbt as vbt  # type: ignore[import-not-found]
        except Exception as exc:  # noqa: BLE001
            return NodeResult(
                status="error",
                error=(
                    "strategy.vbt_portfolio requires vectorbt-pro or vectorbt; "
                    f"neither is installed: {exc}"
                ),
            )

    close = df["close"]
    try:
        if mode == "holding":
            pf = vbt.Portfolio.from_holding(close, init_cash=init_cash, fees=fees)
        elif mode == "signals":
            entries_col = params.get("entries_column") or "entries"
            exits_col = params.get("exits_column") or "exits"
            entries = df.get(entries_col)
            exits = df.get(exits_col)
            if entries is None or exits is None:
                return NodeResult(
                    status="error",
                    error=f"strategy.vbt_portfolio(signals) requires '{entries_col}' + '{exits_col}' columns",
                )
            pf = vbt.Portfolio.from_signals(
                close, entries.astype(bool), exits.astype(bool),
                init_cash=init_cash, fees=fees,
            )
        elif mode == "orders":
            size_col = params.get("size_column") or "size"
            size = df.get(size_col)
            if size is None:
                return NodeResult(
                    status="error",
                    error=f"strategy.vbt_portfolio(orders) requires '{size_col}' column",
                )
            pf = vbt.Portfolio.from_orders(close, size, init_cash=init_cash, fees=fees)
        else:
            return NodeResult(
                status="error",
                error=f"strategy.vbt_portfolio: unknown mode {mode!r}",
            )
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"strategy.vbt_portfolio failed: {exc}")

    # Extract a portable summary + equity curve.
    try:
        equity = pf.value().to_list() if hasattr(pf, "value") else []
    except Exception:  # noqa: BLE001
        equity = []
    try:
        stats = pf.stats()
        stats_dict: dict[str, Any] = (
            {str(k): float(v) for k, v in stats.items() if hasattr(v, "__float__")}
            if hasattr(stats, "items")
            else {}
        )
    except Exception:  # noqa: BLE001
        stats_dict = {}

    locator: dict[str, Any] = {
        "kind": "portfolio_summary",
        "mode": mode,
        "equity_curve": equity,
        "stats": stats_dict,
        "node_id": node.id,
    }
    return NodeResult(
        status="done",
        output_locator=locator,
        metrics={
            "mode": mode,
            "total_return": float(stats_dict.get("Total Return [%]", 0.0)),
            "sharpe": float(stats_dict.get("Sharpe Ratio", 0.0)),
            "max_drawdown": float(stats_dict.get("Max Drawdown [%]", 0.0)),
        },
        log_label=f"vbt_portfolio:{mode}",
    )
