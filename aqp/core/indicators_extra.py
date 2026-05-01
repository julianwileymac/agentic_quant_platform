"""Extra incremental indicators added by the inspiration rehydration.

These are thin ``IndicatorBase`` subclasses that store their state on the
fly so they can be used in a streaming backtest exactly like the
indicators in :mod:`aqp.core.indicators`.

Indicators added:
- ``KST`` — Know Sure Thing (Pring 1992) — momentum oscillator.
- ``RAVI`` — Range Action Verification Index (Chande) — trend filter.
- ``FRAMA`` — Fractal Adaptive Moving Average (Ehlers).
- ``Vortex`` — Vortex Indicator (+VI / -VI cross system).
- ``Fisher`` — Fisher Transform of price.
- ``UlcerIndex`` — Drawdown-based volatility measure.
- ``Coppock`` — Coppock Curve momentum.
- ``MassIndex`` — Mass Index (Dorsey 1996).
- ``MesaSineWave`` — Mesa Sine Wave (Ehlers, sine + lead-sine pair).
- ``Renko`` — Renko brick state (incremental).
- ``ZigZag`` — Direction (+1 / -1) reversal-threshold tracker.
- ``AnchoredVWAP`` — VWAP anchored to a chosen timestamp.
- ``OFI`` — Order Flow Imbalance (signed trade flow).
- ``Microprice`` — quote-weighted micro price.
- ``DepthSlope`` — book-depth slope (cumulative qty vs |price - mid|).

LOB-aware indicators (`OFI`, `Microprice`, `DepthSlope`) only update via
``update_lob(state)`` since they require ``LobState`` not ``BarData``;
when fed bars they return NaN. Most production callers will use them
through :func:`aqp.data.microstructure` directly rather than these
incremental wrappers.
"""
from __future__ import annotations

import math
from collections import deque
from datetime import datetime
from typing import Any

import numpy as np

from aqp.core.indicators import IndicatorBase
from aqp.core.types import BarData


# ---------------------------------------------------------------------------
# Momentum oscillators (KST, Coppock, Fisher, MassIndex)
# ---------------------------------------------------------------------------


class KST(IndicatorBase[BarData]):
    """Know Sure Thing — sum of four smoothed ROCs (Pring 1992).

    Default windows (10, 15, 20, 30) and smooths (10, 10, 10, 15) match
    Pring's original specification.
    """

    name = "KST"

    def __init__(
        self,
        roc_windows: tuple[int, ...] = (10, 15, 20, 30),
        sma_smooths: tuple[int, ...] = (10, 10, 10, 15),
        weights: tuple[float, ...] = (1.0, 2.0, 3.0, 4.0),
        signal_period: int = 9,
    ) -> None:
        super().__init__(period=max(roc_windows) + max(sma_smooths))
        if not (len(roc_windows) == len(sma_smooths) == len(weights)):
            raise ValueError("roc_windows, sma_smooths, weights must be equal length")
        self.roc_windows = roc_windows
        self.sma_smooths = sma_smooths
        self.weights = weights
        self.signal_period = signal_period
        self._closes: deque[float] = deque(maxlen=max(roc_windows) + max(sma_smooths) + 1)
        self.signal: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, _input: BarData, _numeric: float) -> float:
        self._closes.append(_numeric)
        arr = list(self._closes)
        n = len(arr)
        if n < max(self.roc_windows) + max(self.sma_smooths):
            return float("nan")
        kst = 0.0
        for w, s, wt in zip(self.roc_windows, self.sma_smooths, self.weights, strict=False):
            recent = arr[-(w + s):]
            rocs = [(recent[i + w] - recent[i]) / max(abs(recent[i]), 1e-12) for i in range(s)]
            kst += float(np.mean(rocs)) * wt
        return kst


class Coppock(IndicatorBase[BarData]):
    """Coppock Curve — long-term momentum cycle indicator.

    Defaults: WMA(ROC(close, 14) + ROC(close, 11), period=10).
    """

    name = "Coppock"

    def __init__(self, roc_long: int = 14, roc_short: int = 11, wma_period: int = 10) -> None:
        super().__init__(period=roc_long + wma_period)
        self.roc_long = roc_long
        self.roc_short = roc_short
        self.wma_period = wma_period
        self._closes: deque[float] = deque(maxlen=roc_long + wma_period + 1)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, _input: BarData, _numeric: float) -> float:
        self._closes.append(_numeric)
        arr = list(self._closes)
        if len(arr) < self.roc_long + self.wma_period:
            return float("nan")
        roc_l = [(arr[i + self.roc_long] - arr[i]) / max(abs(arr[i]), 1e-12) for i in range(self.wma_period)]
        roc_s = [(arr[i + self.roc_short] - arr[i]) / max(abs(arr[i]), 1e-12) for i in range(self.wma_period)]
        sums = np.add(roc_l, roc_s)
        weights = np.arange(1, self.wma_period + 1, dtype=float)
        return float(np.dot(sums, weights) / weights.sum())


class Fisher(IndicatorBase[BarData]):
    """Fisher Transform of price (Ehlers).

    Maps price to a Gaussian-like distribution; useful for identifying
    extremes.
    """

    name = "Fisher"

    def __init__(self, period: int = 10) -> None:
        super().__init__(period=period)
        self._highs: deque[float] = deque(maxlen=period)
        self._lows: deque[float] = deque(maxlen=period)
        self._prev_value: float = 0.0
        self._prev_fisher: float = 0.0

    def _extract_value(self, value: BarData) -> float:
        return (value.high + value.low) / 2.0

    def compute_next_value(self, input_value: BarData, numeric: float) -> float:
        self._highs.append(input_value.high)
        self._lows.append(input_value.low)
        if len(self._highs) < self.period:
            return float("nan")
        max_h = max(self._highs)
        min_l = min(self._lows)
        if max_h == min_l:
            normalised = 0.0
        else:
            normalised = 0.66 * ((numeric - min_l) / (max_h - min_l) - 0.5) + 0.67 * self._prev_value
        normalised = max(min(normalised, 0.999), -0.999)
        fisher = 0.5 * math.log((1 + normalised) / (1 - normalised)) + 0.5 * self._prev_fisher
        self._prev_value = normalised
        self._prev_fisher = fisher
        return fisher


class MassIndex(IndicatorBase[BarData]):
    """Mass Index (Dorsey 1996) — reversal warning via range expansion.

    Sums the EMA(EMA(high - low) ratio) over a 25-bar window.
    """

    name = "MassIndex"

    def __init__(self, ema_period: int = 9, sum_period: int = 25) -> None:
        super().__init__(period=sum_period)
        self.ema_period = ema_period
        self.sum_period = sum_period
        self._ranges: deque[float] = deque(maxlen=ema_period * 4)
        self._ratios: deque[float] = deque(maxlen=sum_period)
        self._ema_single: float = float("nan")
        self._ema_double: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.high - value.low

    def compute_next_value(self, _input: BarData, numeric: float) -> float:
        self._ranges.append(numeric)
        alpha = 2.0 / (self.ema_period + 1)
        self._ema_single = numeric if math.isnan(self._ema_single) else alpha * numeric + (1 - alpha) * self._ema_single
        self._ema_double = self._ema_single if math.isnan(self._ema_double) else alpha * self._ema_single + (1 - alpha) * self._ema_double
        if abs(self._ema_double) < 1e-12:
            ratio = float("nan")
        else:
            ratio = self._ema_single / self._ema_double
        if not math.isnan(ratio):
            self._ratios.append(ratio)
        if len(self._ratios) < self.sum_period:
            return float("nan")
        return float(sum(self._ratios))


# ---------------------------------------------------------------------------
# Trend / adaptive
# ---------------------------------------------------------------------------


class FRAMA(IndicatorBase[BarData]):
    """Fractal Adaptive Moving Average (Ehlers)."""

    name = "FRAMA"

    def __init__(self, period: int = 16, fc: float = 4.6, sc: float = 200.0) -> None:
        if period % 2 != 0:
            period += 1
        super().__init__(period=period)
        self.fc = fc
        self.sc = sc
        self._closes: deque[float] = deque(maxlen=period * 2)
        self._frama: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, numeric: float) -> float:
        self._closes.append(input_value.high)  # uses HL
        if len(self._closes) < self.period:
            return float("nan")
        n = self.period
        h1 = max(list(self._closes)[-n // 2:])
        l1 = min(list(self._closes)[-n // 2:])
        h2 = max(list(self._closes)[-n: -n // 2])
        l2 = min(list(self._closes)[-n: -n // 2])
        h_total = max(h1, h2)
        l_total = min(l1, l2)
        n1 = (h1 - l1) / (n / 2) if (n / 2) > 0 else 0
        n2 = (h2 - l2) / (n / 2) if (n / 2) > 0 else 0
        n3 = (h_total - l_total) / n if n > 0 else 0
        if n1 + n2 <= 0 or n3 <= 0:
            d = 1.0
        else:
            d = (math.log(n1 + n2) - math.log(n3)) / math.log(2)
        alpha = math.exp(-self.fc * (d - 1))
        alpha = max(2.0 / (self.sc + 1), min(alpha, 1.0))
        if math.isnan(self._frama):
            self._frama = numeric
        else:
            self._frama = alpha * numeric + (1 - alpha) * self._frama
        return self._frama


class Vortex(IndicatorBase[BarData]):
    """Vortex Indicator (+VI / -VI). ``current`` returns +VI - -VI."""

    name = "Vortex"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._tr: deque[float] = deque(maxlen=period)
        self._vp: deque[float] = deque(maxlen=period)
        self._vm: deque[float] = deque(maxlen=period)
        self._prev_close: float | None = None
        self._prev_high: float | None = None
        self._prev_low: float | None = None
        self.plus_vi: float = float("nan")
        self.minus_vi: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        if self._prev_close is None:
            self._prev_close = input_value.close
            self._prev_high = input_value.high
            self._prev_low = input_value.low
            return float("nan")
        tr = max(
            input_value.high - input_value.low,
            abs(input_value.high - self._prev_close),
            abs(input_value.low - self._prev_close),
        )
        vp = abs(input_value.high - self._prev_low)
        vm = abs(input_value.low - self._prev_high)
        self._tr.append(tr)
        self._vp.append(vp)
        self._vm.append(vm)
        self._prev_close = input_value.close
        self._prev_high = input_value.high
        self._prev_low = input_value.low
        if len(self._tr) < self.period:
            return float("nan")
        sum_tr = sum(self._tr)
        if sum_tr <= 0:
            return float("nan")
        self.plus_vi = sum(self._vp) / sum_tr
        self.minus_vi = sum(self._vm) / sum_tr
        return self.plus_vi - self.minus_vi


# ---------------------------------------------------------------------------
# Range / volatility
# ---------------------------------------------------------------------------


class RAVI(IndicatorBase[BarData]):
    """Range Action Verification Index (Chande).

    100 * |SMA(close, fast) - SMA(close, slow)| / SMA(close, slow).
    Above 3 typically = trending; below = ranging.
    """

    name = "RAVI"

    def __init__(self, fast: int = 7, slow: int = 65) -> None:
        super().__init__(period=slow)
        self.fast = fast
        self.slow = slow
        self._closes: deque[float] = deque(maxlen=slow)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, _input: BarData, numeric: float) -> float:
        self._closes.append(numeric)
        if len(self._closes) < self.slow:
            return float("nan")
        arr = list(self._closes)
        sma_fast = float(np.mean(arr[-self.fast:]))
        sma_slow = float(np.mean(arr))
        if abs(sma_slow) < 1e-12:
            return float("nan")
        return 100.0 * abs(sma_fast - sma_slow) / abs(sma_slow)


class UlcerIndex(IndicatorBase[BarData]):
    """Ulcer Index — RMS of percentage drawdowns over a window."""

    name = "UlcerIndex"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._closes: deque[float] = deque(maxlen=period)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, _input: BarData, numeric: float) -> float:
        self._closes.append(numeric)
        if len(self._closes) < self.period:
            return float("nan")
        arr = np.array(self._closes)
        running_max = np.maximum.accumulate(arr)
        dd = 100.0 * (arr - running_max) / running_max
        return float(math.sqrt(float(np.mean(dd ** 2))))


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------


class MesaSineWave(IndicatorBase[BarData]):
    """Mesa Sine Wave (Ehlers) — sine + lead-sine pair via Hilbert proxy.

    Simplified incremental implementation: tracks instantaneous phase from
    rolling autocorrelation and emits sin(phase) as ``current``.
    """

    name = "MesaSineWave"

    def __init__(self, period: int = 16) -> None:
        super().__init__(period=period)
        self._closes: deque[float] = deque(maxlen=period * 2)
        self.sine: float = float("nan")
        self.lead_sine: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, _input: BarData, numeric: float) -> float:
        self._closes.append(numeric)
        if len(self._closes) < self.period * 2:
            return float("nan")
        arr = np.array(self._closes) - np.mean(self._closes)
        # phase via FFT peak
        spec = np.abs(np.fft.rfft(arr))
        if spec.size <= 1:
            return float("nan")
        peak = int(np.argmax(spec[1:]) + 1)
        if peak <= 0:
            return float("nan")
        phase = 2.0 * math.pi * (len(arr) % (len(arr) / peak)) / (len(arr) / peak)
        self.sine = math.sin(phase)
        self.lead_sine = math.sin(phase + math.pi / 4)
        return self.sine


# ---------------------------------------------------------------------------
# Chart-type and ZigZag
# ---------------------------------------------------------------------------


class Renko(IndicatorBase[BarData]):
    """Renko brick state.

    ``current`` returns the latest brick close. ``brick_size`` defaults
    to 1.0 in price units (caller should size relative to ATR).
    """

    name = "Renko"

    def __init__(self, brick_size: float = 1.0) -> None:
        super().__init__(period=1)
        self.brick_size = float(brick_size)
        self._last_brick: float | None = None
        self.direction: int = 0  # +1 up, -1 down, 0 unset

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, _input: BarData, numeric: float) -> float:
        if self._last_brick is None:
            self._last_brick = numeric
            return numeric
        diff = numeric - self._last_brick
        if abs(diff) >= self.brick_size:
            n = int(diff / self.brick_size)
            self._last_brick = self._last_brick + n * self.brick_size
            self.direction = 1 if n > 0 else -1
        return float(self._last_brick)


class ZigZag(IndicatorBase[BarData]):
    """ZigZag direction tracker.

    ``current`` returns +1 for upswing, -1 for downswing, 0 for the
    initial neutral period.
    """

    name = "ZigZag"

    def __init__(self, threshold_pct: float = 0.05) -> None:
        super().__init__(period=1)
        self.threshold_pct = float(threshold_pct)
        self._pivot: float | None = None
        self._direction: int = 0

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, _input: BarData, numeric: float) -> float:
        if self._pivot is None:
            self._pivot = numeric
            return 0.0
        change = (numeric - self._pivot) / self._pivot
        if self._direction == 0:
            if change >= self.threshold_pct:
                self._direction = 1
                self._pivot = numeric
            elif change <= -self.threshold_pct:
                self._direction = -1
                self._pivot = numeric
        elif self._direction == 1:
            if numeric > self._pivot:
                self._pivot = numeric
            elif (numeric - self._pivot) / self._pivot <= -self.threshold_pct:
                self._direction = -1
                self._pivot = numeric
        else:
            if numeric < self._pivot:
                self._pivot = numeric
            elif (numeric - self._pivot) / self._pivot >= self.threshold_pct:
                self._direction = 1
                self._pivot = numeric
        return float(self._direction)


# ---------------------------------------------------------------------------
# Anchored VWAP
# ---------------------------------------------------------------------------


class AnchoredVWAP(IndicatorBase[BarData]):
    """VWAP anchored to a chosen ``anchor_timestamp``.

    Until the anchor time is reached the indicator returns NaN. From the
    anchor onward it accumulates ``sum(price * volume) / sum(volume)``.
    """

    name = "AnchoredVWAP"

    def __init__(self, anchor_timestamp: datetime | None = None) -> None:
        super().__init__(period=1)
        self.anchor_timestamp = anchor_timestamp
        self._cum_pv: float = 0.0
        self._cum_v: float = 0.0
        self._anchored: bool = anchor_timestamp is None

    def _extract_value(self, value: BarData) -> float:
        return (value.high + value.low + value.close) / 3.0

    def compute_next_value(self, input_value: BarData, numeric: float) -> float:
        if not self._anchored and input_value.timestamp >= self.anchor_timestamp:
            self._anchored = True
        if not self._anchored:
            return float("nan")
        self._cum_pv += numeric * input_value.volume
        self._cum_v += input_value.volume
        if self._cum_v <= 0:
            return float("nan")
        return self._cum_pv / self._cum_v

    def reset_anchor(self, ts: datetime | None) -> None:
        self.anchor_timestamp = ts
        self._anchored = ts is None
        self._cum_pv = 0.0
        self._cum_v = 0.0


# ---------------------------------------------------------------------------
# LOB-aware indicators (BarData input emits NaN; use update_lob)
# ---------------------------------------------------------------------------


class _LobIndicatorBase(IndicatorBase[BarData]):
    """Common base for LOB-only indicators."""

    def __init__(self) -> None:
        super().__init__(period=1)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, _input: BarData, _numeric: float) -> float:
        return float("nan")

    def update_lob(self, state: Any) -> float:
        """Subclasses override; ``state`` is a :class:`aqp.strategies.lob.LobState`."""
        return float("nan")


class OFI(_LobIndicatorBase):
    """Order Flow Imbalance — signed trade flow at the top of book."""

    name = "OFI"

    def update_lob(self, state: Any) -> float:
        bq = float(getattr(state, "bid_qty", 0))
        aq = float(getattr(state, "ask_qty", 0))
        out = (bq - aq) / (bq + aq + 1e-12)
        self.current = out
        self.samples += 1
        return out


class Microprice(_LobIndicatorBase):
    """Micro price ``(P_ask * Q_bid + P_bid * Q_ask) / (Q_bid + Q_ask)``."""

    name = "Microprice"

    def update_lob(self, state: Any) -> float:
        bp = float(getattr(state, "best_bid", 0))
        ap = float(getattr(state, "best_ask", 0))
        bq = float(getattr(state, "bid_qty", 0))
        aq = float(getattr(state, "ask_qty", 0))
        denom = bq + aq + 1e-12
        out = (ap * bq + bp * aq) / denom
        self.current = out
        self.samples += 1
        return out


class DepthSlope(_LobIndicatorBase):
    """Linear slope of cumulative qty vs |price - mid| across depth levels."""

    name = "DepthSlope"

    def update_lob(self, state: Any) -> float:
        prices = getattr(state, "bid_prices", None)
        qtys = getattr(state, "bid_qtys", None)
        if prices is None or qtys is None or len(prices) < 2:
            return float("nan")
        mid = state.mid_price
        x = np.abs(np.asarray(prices, dtype=float) - mid)
        y = np.cumsum(np.asarray(qtys, dtype=float))
        if x.std() < 1e-12:
            return float("nan")
        slope = float(np.cov(x, y, ddof=0)[0, 1] / (x.var() + 1e-12))
        self.current = slope
        self.samples += 1
        return slope


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


EXTRA_INDICATORS: dict[str, type[IndicatorBase]] = {
    "KST": KST,
    "RAVI": RAVI,
    "FRAMA": FRAMA,
    "Vortex": Vortex,
    "Fisher": Fisher,
    "UlcerIndex": UlcerIndex,
    "Coppock": Coppock,
    "MassIndex": MassIndex,
    "MesaSineWave": MesaSineWave,
    "Renko": Renko,
    "ZigZag": ZigZag,
    "AnchoredVWAP": AnchoredVWAP,
    "OFI": OFI,
    "Microprice": Microprice,
    "DepthSlope": DepthSlope,
}


def install() -> None:
    """Append the extra indicators into :data:`aqp.core.indicators.ALL_INDICATORS`."""
    from aqp.core import indicators as _ind

    for name, cls in EXTRA_INDICATORS.items():
        _ind.ALL_INDICATORS.setdefault(name, cls)


# Auto-install on import so callers can ``from aqp.core import indicators_extra``
# and immediately use the new names via ``build_indicator``.
install()


__all__ = [
    "EXTRA_INDICATORS",
    "AnchoredVWAP",
    "Coppock",
    "DepthSlope",
    "FRAMA",
    "Fisher",
    "KST",
    "MassIndex",
    "MesaSineWave",
    "Microprice",
    "OFI",
    "RAVI",
    "Renko",
    "UlcerIndex",
    "Vortex",
    "ZigZag",
    "install",
]
