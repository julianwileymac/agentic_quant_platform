"""Build wide-format signal arrays for ``Portfolio.from_signals``.

The vbt-pro engine accepts boolean ``entries`` / ``exits`` (and optional
``short_entries`` / ``short_exits``) DataFrames in wide format (rows =
timestamp, columns = vt_symbol). AQP's :class:`IAlphaModel` emits sparse
:class:`Signal` insights — this module bridges the two shapes.

Two paths are supported:

1. **Per-bar loop** (default): replay history one timestamp at a time and
   call ``alpha.generate_signals(history, universe, ctx)`` on the rolling
   window. This is the legacy path and works with every existing alpha.
2. **Panel path** (opt-in): if the alpha implements
   ``generate_panel_signals(bars, universe, context) -> SignalArrays``, the
   builder uses that directly. ML and agentic alphas implement this for
   speed (single panel-wide forward pass / batch agent dispatch).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel, IStrategy
from aqp.core.types import Direction, Symbol

logger = logging.getLogger(__name__)


@dataclass
class SignalArrays:
    """Wide-format signal arrays consumed by ``Portfolio.from_signals``.

    Every frame shares the same index (timestamps) and columns (vt_symbols).
    Booleans default to ``False`` so callers can leave any of the
    ``short_*`` frames as ``None`` for long-only strategies.
    """

    entries: pd.DataFrame
    exits: pd.DataFrame
    short_entries: pd.DataFrame | None = None
    short_exits: pd.DataFrame | None = None

    # Optional rich extensions vbt-pro accepts:
    size: pd.DataFrame | None = None
    price: pd.DataFrame | None = None
    sl_stop: pd.DataFrame | float | None = None
    tsl_stop: pd.DataFrame | float | None = None
    tp_stop: pd.DataFrame | float | None = None

    # Free-form per-bar signal records the runner can attach to BacktestResult
    signal_records: list[dict[str, Any]] = field(default_factory=list)

    def has_shorts(self) -> bool:
        if self.short_entries is None or self.short_exits is None:
            return False
        return bool(self.short_entries.any().any() or self.short_exits.any().any())


def _resolve_alpha(strategy: IAlphaModel | IStrategy | Any) -> IAlphaModel:
    """Return the alpha stage of a framework algorithm or the strategy itself."""
    if hasattr(strategy, "alpha_model"):
        return strategy.alpha_model  # type: ignore[attr-defined]
    return strategy


def build_signal_arrays(
    strategy: IAlphaModel | IStrategy | Any,
    bars: pd.DataFrame,
    close: pd.DataFrame,
    *,
    allow_short: bool = True,
    warmup_bars: int = 30,
    record_signals: bool = True,
) -> SignalArrays:
    """Build :class:`SignalArrays` from a strategy + bars frame.

    Parameters
    ----------
    strategy:
        Either an :class:`IAlphaModel` directly, or a framework-style strategy
        whose ``alpha_model`` attribute exposes one.
    bars:
        Tidy long bars frame — used both for symbol enumeration and as the
        rolling history fed to ``alpha.generate_signals`` per timestamp.
    close:
        Wide close panel from :func:`aqp.backtest.vbtpro.data_utils.pivot_close`
        — defines the index and columns of the resulting arrays.
    allow_short:
        When ``False`` short signals are squashed into "no-op" so a long-only
        strategy does not accidentally emit shorts.
    warmup_bars:
        Number of leading bars to skip before letting the alpha emit signals.
    record_signals:
        Capture per-bar signal metadata so the runner can populate
        :class:`BacktestResult.signals`. Disable for huge sweeps where the
        Python list bookkeeping is hot.
    """
    alpha = _resolve_alpha(strategy)

    if hasattr(alpha, "generate_panel_signals"):
        try:
            arr = alpha.generate_panel_signals(
                bars,
                _universe(bars),
                {"close": close, "allow_short": allow_short},
            )
        except Exception:
            logger.exception(
                "alpha.generate_panel_signals failed; falling back to per-bar"
            )
        else:
            if isinstance(arr, SignalArrays):
                return arr
            return _coerce_to_signal_arrays(arr, close, allow_short=allow_short)

    return _build_from_per_bar_loop(
        alpha,
        bars=bars,
        close=close,
        allow_short=allow_short,
        warmup_bars=warmup_bars,
        record_signals=record_signals,
    )


def _universe(bars: pd.DataFrame) -> list[Symbol]:
    out: list[Symbol] = []
    for vt in sorted(bars["vt_symbol"].unique()):
        try:
            out.append(Symbol.parse(vt))
        except Exception:
            continue
    return out


def _build_from_per_bar_loop(
    alpha: IAlphaModel,
    *,
    bars: pd.DataFrame,
    close: pd.DataFrame,
    allow_short: bool,
    warmup_bars: int,
    record_signals: bool,
) -> SignalArrays:
    entries = pd.DataFrame(False, index=close.index, columns=close.columns)
    exits = pd.DataFrame(False, index=close.index, columns=close.columns)
    short_entries = pd.DataFrame(False, index=close.index, columns=close.columns)
    short_exits = pd.DataFrame(False, index=close.index, columns=close.columns)

    sorted_frame = bars.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)
    history_mask = pd.Series(False, index=sorted_frame.index)
    state: dict[str, Direction] = {}
    universe = _universe(bars)
    records: list[dict[str, Any]] = []

    for i, ts in enumerate(close.index):
        if i < warmup_bars:
            continue
        day_mask = sorted_frame["timestamp"] == ts
        history_mask |= day_mask
        history_view = sorted_frame[history_mask]
        ctx: dict[str, Any] = {"current_time": ts.to_pydatetime()}

        try:
            signals = alpha.generate_signals(history_view, universe, ctx)
        except Exception:  # pragma: no cover - defensive
            logger.exception("alpha.generate_signals failed at %s", ts)
            continue

        for sig in signals:
            vt = sig.symbol.vt_symbol
            if vt not in close.columns:
                continue
            current = state.get(vt)
            direction = sig.direction
            if direction == Direction.LONG:
                if current != Direction.LONG:
                    entries.at[ts, vt] = True
                    if current == Direction.SHORT:
                        short_exits.at[ts, vt] = True
                    state[vt] = Direction.LONG
            elif direction == Direction.SHORT and allow_short:
                if current != Direction.SHORT:
                    short_entries.at[ts, vt] = True
                    if current == Direction.LONG:
                        exits.at[ts, vt] = True
                    state[vt] = Direction.SHORT
            elif direction == Direction.NET:
                if current == Direction.LONG:
                    exits.at[ts, vt] = True
                elif current == Direction.SHORT:
                    short_exits.at[ts, vt] = True
                state[vt] = Direction.NET

            if record_signals:
                records.append(
                    {
                        "timestamp": ts,
                        "vt_symbol": vt,
                        "direction": direction.value
                        if hasattr(direction, "value")
                        else str(direction),
                        "strength": float(getattr(sig, "strength", 0.0)),
                        "confidence": float(getattr(sig, "confidence", 0.0)),
                        "horizon_days": int(getattr(sig, "horizon_days", 0)),
                        "source": getattr(sig, "source", ""),
                    }
                )

    return SignalArrays(
        entries=entries,
        exits=exits,
        short_entries=short_entries if allow_short else None,
        short_exits=short_exits if allow_short else None,
        signal_records=records,
    )


def _coerce_to_signal_arrays(
    raw: Any,
    close: pd.DataFrame,
    *,
    allow_short: bool,
) -> SignalArrays:
    """Best-effort conversion of a duck-typed payload into :class:`SignalArrays`."""

    def _as_bool_df(value: Any) -> pd.DataFrame:
        if value is None:
            return pd.DataFrame(False, index=close.index, columns=close.columns)
        if isinstance(value, pd.DataFrame):
            return value.reindex(index=close.index, columns=close.columns).fillna(False).astype(bool)
        return pd.DataFrame(value, index=close.index, columns=close.columns).astype(bool)

    entries = _as_bool_df(getattr(raw, "entries", None))
    exits = _as_bool_df(getattr(raw, "exits", None))
    short_entries = _as_bool_df(getattr(raw, "short_entries", None)) if allow_short else None
    short_exits = _as_bool_df(getattr(raw, "short_exits", None)) if allow_short else None
    return SignalArrays(
        entries=entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=short_exits,
        size=getattr(raw, "size", None),
        price=getattr(raw, "price", None),
        sl_stop=getattr(raw, "sl_stop", None),
        tsl_stop=getattr(raw, "tsl_stop", None),
        tp_stop=getattr(raw, "tp_stop", None),
        signal_records=list(getattr(raw, "signal_records", []) or []),
    )


__all__ = ["SignalArrays", "build_signal_arrays"]
