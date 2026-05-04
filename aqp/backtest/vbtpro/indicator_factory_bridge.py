"""Bridge AQP's :class:`IndicatorBase` zoo into vbt-pro ``IndicatorFactory``.

vbt-pro's :class:`IndicatorFactory` produces classes that play nicely with
vectorised backtests, parameter sweeps (``vbt.Param``), and multi-asset
broadcasting. AQP indicators are *online* (per-bar) state machines designed
for streaming data; this bridge wraps them so they're available inside the
vbt-pro ecosystem.

Usage::

    from aqp.backtest.vbtpro.indicator_factory_bridge import vbt_indicator
    sma = vbt_indicator("SMA")  # vbt-pro IndicatorFactory class
    out = sma.run(close, period=[10, 20, 50])

The returned object has a ``Param``-friendly column index, so you can plug it
into ``Portfolio.from_signals`` and run a sweep across windows in one shot.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np
import pandas as pd

from aqp.backtest.vectorbt_backend import import_vectorbtpro
from aqp.core.indicators import ALL_INDICATORS, IndicatorBase
from aqp.data.indicators_zoo import _EXTRA_OUTPUTS

logger = logging.getLogger(__name__)


def _resolve_class(name: str) -> type[IndicatorBase]:
    if name in ALL_INDICATORS:
        return ALL_INDICATORS[name]
    raise KeyError(
        f"Unknown AQP indicator {name!r}. "
        f"Known: {sorted(ALL_INDICATORS.keys())}."
    )


def _output_names(cls: type[IndicatorBase]) -> list[str]:
    """Per-row outputs we surface on the resulting vbt-pro IndicatorFactory."""
    extras = _EXTRA_OUTPUTS.get(cls, [])
    return ["value", *extras]


def _apply_indicator(
    cls: type[IndicatorBase],
    close: np.ndarray,
    high: np.ndarray | None,
    low: np.ndarray | None,
    **kwargs: Any,
) -> tuple[np.ndarray, ...]:
    """Run an AQP indicator across one column and surface every output stream."""
    indicator = cls(**kwargs)
    extras = _EXTRA_OUTPUTS.get(cls, [])
    n = len(close)
    out = {"value": np.full(n, np.nan, dtype=float)}
    for name in extras:
        out[name] = np.full(n, np.nan, dtype=float)

    use_hl = high is not None and low is not None and "update_with_bar" in dir(indicator)
    for i in range(n):
        try:
            if use_hl:
                value = indicator.update_with_bar(  # type: ignore[attr-defined]
                    close=float(close[i]),
                    high=float(high[i]),
                    low=float(low[i]),
                )
            else:
                value = indicator.update(float(close[i]))
        except Exception:
            value = np.nan
        out["value"][i] = float(value) if value is not None else np.nan
        for name in extras:
            attr = getattr(indicator, name, None)
            if attr is None:
                continue
            try:
                out[name][i] = float(attr) if attr is not None else np.nan
            except Exception:
                out[name][i] = np.nan
    return tuple(out[name] for name in ["value", *extras])


def _custom_func(cls: type[IndicatorBase]) -> Callable[..., Any]:
    extras = _EXTRA_OUTPUTS.get(cls, [])

    def _func(close: np.ndarray, *args: Any, **kwargs: Any) -> Any:
        # vbt-pro's IndicatorFactory passes optional input arrays positionally.
        # We accept ``high`` / ``low`` for indicators that need them.
        high = kwargs.pop("high", None)
        low = kwargs.pop("low", None)
        if close.ndim == 1:
            cols = [close]
            highs = [high] if high is not None else [None]
            lows = [low] if low is not None else [None]
        else:
            cols = [close[:, i] for i in range(close.shape[1])]
            highs = (
                [high[:, i] for i in range(high.shape[1])]
                if isinstance(high, np.ndarray)
                else [None] * close.shape[1]
            )
            lows = (
                [low[:, i] for i in range(low.shape[1])]
                if isinstance(low, np.ndarray)
                else [None] * close.shape[1]
            )

        outputs: list[list[np.ndarray]] = [[] for _ in ["value", *extras]]
        for c, h, l_ in zip(cols, highs, lows, strict=True):
            streams = _apply_indicator(cls, c, h, l_, **kwargs)
            for slot, stream in zip(outputs, streams, strict=True):
                slot.append(stream)

        stacked = [
            np.column_stack(slot) if close.ndim == 2 else slot[0]
            for slot in outputs
        ]
        return tuple(stacked) if extras else stacked[0]

    return _func


def vbt_indicator(name: str, *, short_name: str | None = None) -> Any:
    """Return a vbt-pro ``IndicatorFactory`` class wrapping an AQP indicator.

    The resulting class accepts:

    - ``close`` (required): wide-format close panel.
    - ``high`` / ``low`` (optional kwargs): for ATR-like indicators.
    - any indicator constructor kwargs as ``Param``-able parameters.

    Example::

        sma = vbt_indicator("SMA")
        out = sma.run(close, period=[10, 20, 50])
        sma_10 = out.value[(slice(None), 10)]
    """
    cls = _resolve_class(name)
    vbt = import_vectorbtpro().module
    extras = _EXTRA_OUTPUTS.get(cls, [])

    factory = vbt.IndicatorFactory(
        class_name=f"AQPv_{name}",
        short_name=short_name or name.lower(),
        input_names=["close"],
        param_names=_param_names(cls),
        output_names=["value", *extras],
    )
    return factory.with_custom_func(_custom_func(cls))


def _param_names(cls: type[IndicatorBase]) -> list[str]:
    """Best-effort: introspect the indicator's __init__ for parameter names.

    Returns the constructor-arg names except ``self`` so they show up as
    ``Param``-able knobs on the factory.
    """
    import inspect

    try:
        sig = inspect.signature(cls)
    except (TypeError, ValueError):
        return []
    out: list[str] = []
    for name, param in sig.parameters.items():
        if name in ("self", "args", "kwargs"):
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        out.append(name)
    return out


def register_all_indicators_with_vbt() -> dict[str, Any]:
    """Build a vbt-pro IndicatorFactory class for every AQP indicator.

    Returns a ``{name: IndicatorClass}`` mapping. Useful when bootstrapping a
    research notebook so the user does not have to call :func:`vbt_indicator`
    one indicator at a time.
    """
    return {name: vbt_indicator(name) for name in ALL_INDICATORS}


__all__ = [
    "vbt_indicator",
    "register_all_indicators_with_vbt",
]
