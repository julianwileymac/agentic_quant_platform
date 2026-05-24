"""``feature.technical`` — TA-Lib / vbt-style indicators over OHLCV.

Phase 2 ships SMA / EMA / RSI / MACD / Bollinger / ATR. The full
``indicators_zoo`` catalog (50+ indicators wrapping vbt-pro) is
mounted in Phase 3 when the param schema gets the JSON Schema treatment.

Params:

- ``indicator`` (str, required) — one of ``sma`` / ``ema`` / ``rsi`` /
  ``macd`` / ``bollinger`` / ``atr``.
- ``window`` (int) — primary window.
- ``column`` (str, default ``"close"``).
- ``alias`` (str | None) — output column name; defaults to
  ``{indicator}_{window}``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).mean()


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd = _ema(s, fast) - _ema(s, slow)
    sig = _ema(macd, signal)
    return pd.DataFrame({"macd": macd, "macd_signal": sig, "macd_hist": macd - sig})


def _bollinger(s: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = _sma(s, n)
    std = s.rolling(n).std()
    return pd.DataFrame({"bb_mid": mid, "bb_up": mid + k * std, "bb_low": mid - k * std})


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n, min_periods=1).mean()


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    indicator = str(params.get("indicator") or "sma").lower()
    window = int(params.get("window") or 14)
    column = str(params.get("column") or "close")
    alias = str(params.get("alias") or f"{indicator}_{window}")

    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(status="error", error="feature.technical needs an upstream OHLCV frame")
    out = df.copy()
    if column not in out.columns:
        return NodeResult(
            status="error",
            error=f"feature.technical: column {column!r} missing from upstream",
        )

    try:
        if indicator == "sma":
            out[alias] = _sma(out[column], window)
        elif indicator == "ema":
            out[alias] = _ema(out[column], window)
        elif indicator == "rsi":
            out[alias] = _rsi(out[column], window)
        elif indicator == "macd":
            sub = _macd(out[column])
            out = pd.concat([out, sub], axis=1)
        elif indicator == "bollinger":
            sub = _bollinger(out[column], window)
            out = pd.concat([out, sub], axis=1)
        elif indicator == "atr":
            if not all(c in out.columns for c in ("high", "low", "close")):
                return NodeResult(
                    status="error",
                    error="feature.technical(atr) needs high / low / close columns",
                )
            out[alias] = _atr(out["high"], out["low"], out["close"], window)
        else:
            return NodeResult(
                status="error",
                error=f"feature.technical: unknown indicator {indicator!r}",
            )
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"feature.technical failed: {exc}")
    stash_arrow_output(ctx, node.id, out)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out),
            "indicator": indicator,
            "window": window,
        },
        metrics={"indicator": indicator, "window": window},
        log_label=f"technical:{indicator}({window})",
    )
