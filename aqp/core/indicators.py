"""Online technical indicators — Lean's ``IndicatorBase`` / ``RollingWindow`` pattern.

Every indicator is an **incremental** state machine: you push a value (or
``BarData``) with :meth:`IndicatorBase.update` and read :attr:`current`.
That matches Lean exactly and lets the same indicator run on a batched
backtest and a streaming paper session without any API difference.

Pure-pandas / pure-numpy implementations so the base install stays lean;
install TA-Lib separately if you want the FFI-accelerated versions — the
high-level :mod:`aqp.data.indicators_zoo` helpers prefer TA-Lib when
available and fall back to these classes transparently.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from aqp.core.types import BarData

T = TypeVar("T")


# ---------------------------------------------------------------------------
# RollingWindow
# ---------------------------------------------------------------------------


class RollingWindow(Generic[T]):
    """Fixed-size ring buffer (Lean ``RollingWindow<T>``).

    ``window[0]`` is the most recent value; ``window[size-1]`` is the
    oldest. Unfilled positions raise ``IndexError``.
    """

    def __init__(self, size: int) -> None:
        if size <= 0:
            raise ValueError("window size must be positive")
        self.size = int(size)
        self._buf: deque[T] = deque(maxlen=self.size)

    def add(self, value: T) -> None:
        self._buf.appendleft(value)

    def __getitem__(self, i: int) -> T:
        return self._buf[i]

    def __len__(self) -> int:
        return len(self._buf)

    @property
    def count(self) -> int:
        return len(self._buf)

    @property
    def is_ready(self) -> bool:
        return len(self._buf) == self.size

    def to_list(self) -> list[T]:
        return list(self._buf)

    def reset(self) -> None:
        self._buf.clear()


# ---------------------------------------------------------------------------
# IndicatorBase
# ---------------------------------------------------------------------------


@dataclass
class IndicatorDataPoint:
    timestamp: datetime
    value: float


class IndicatorBase(ABC, Generic[T]):
    """Base class for every indicator.

    Subclasses override :meth:`compute_next_value`. The caller feeds input
    via :meth:`update`; the indicator's ``current`` value is always the
    most recent output, ``previous`` the one before it.
    """

    name: str = "indicator"

    def __init__(self, period: int = 0) -> None:
        self.period = int(period)
        self.samples: int = 0
        self.current: float = float("nan")
        self.previous: float = float("nan")
        self.window: RollingWindow[IndicatorDataPoint] = RollingWindow(max(period, 2))

    @property
    def is_ready(self) -> bool:
        return self.samples >= self.period and not math.isnan(self.current)

    def reset(self) -> None:
        self.samples = 0
        self.current = float("nan")
        self.previous = float("nan")
        self.window.reset()

    def update(self, value: T, timestamp: datetime | None = None) -> float:
        """Feed the indicator one input; returns the new ``current``."""
        self.samples += 1
        self.previous = self.current
        numeric = self._extract_value(value)
        self.current = self.compute_next_value(value, numeric)
        ts = timestamp or datetime.utcnow()
        if not math.isnan(self.current):
            self.window.add(IndicatorDataPoint(ts, self.current))
        return self.current

    @abstractmethod
    def compute_next_value(self, input_value: T, numeric: float) -> float:
        """Override with the indicator's math. ``numeric`` is ``_extract_value(input_value)``."""

    def _extract_value(self, value: T) -> float:
        if isinstance(value, BarData):
            return float(value.close)
        if isinstance(value, (int, float)):
            return float(value)
        raise TypeError(f"{self.name}: cannot extract numeric from {type(value).__name__}")


Indicator = IndicatorBase[float]


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------


class SimpleMovingAverage(IndicatorBase[float]):
    name = "SMA"

    def __init__(self, period: int) -> None:
        super().__init__(period=period)
        self._buf: deque[float] = deque(maxlen=period)
        self._sum = 0.0

    def compute_next_value(self, _input: float, numeric: float) -> float:
        if len(self._buf) == self._buf.maxlen:
            self._sum -= self._buf[0]
        self._buf.append(numeric)
        self._sum += numeric
        if len(self._buf) < self.period:
            return float("nan")
        return self._sum / self.period

    def reset(self) -> None:
        super().reset()
        self._buf.clear()
        self._sum = 0.0


class ExponentialMovingAverage(IndicatorBase[float]):
    name = "EMA"

    def __init__(self, period: int) -> None:
        super().__init__(period=period)
        self.alpha = 2.0 / (period + 1)

    def compute_next_value(self, _input: float, numeric: float) -> float:
        if math.isnan(self.current):
            return numeric
        return self.alpha * numeric + (1 - self.alpha) * self.current


class HullMovingAverage(IndicatorBase[float]):
    """Hull MA: WMA(2 * WMA(n/2) - WMA(n)) over sqrt(n)."""

    name = "HMA"

    def __init__(self, period: int) -> None:
        super().__init__(period=period)
        self._buf: deque[float] = deque(maxlen=period)

    def _wma(self, data: list[float], period: int) -> float:
        tail = data[-period:]
        if len(tail) < period:
            return float("nan")
        denom = period * (period + 1) / 2
        return sum((i + 1) * v for i, v in enumerate(tail)) / denom

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self._buf.append(numeric)
        data = list(self._buf)
        if len(data) < self.period:
            return float("nan")
        half = int(self.period / 2)
        sqrt_n = int(math.sqrt(self.period))
        wma_half = self._wma(data, half)
        wma_full = self._wma(data, self.period)
        raw = 2 * wma_half - wma_full
        self._buf.append(raw)
        result = self._wma(list(self._buf), sqrt_n)
        self._buf.pop()
        return result


class KAMA(IndicatorBase[float]):
    """Kaufman's Adaptive Moving Average."""

    name = "KAMA"

    def __init__(self, period: int = 10, fast: int = 2, slow: int = 30) -> None:
        super().__init__(period=period)
        self.fast = fast
        self.slow = slow
        self._buf: deque[float] = deque(maxlen=period + 1)

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self._buf.append(numeric)
        if len(self._buf) < self.period + 1:
            return float("nan")
        change = abs(self._buf[-1] - self._buf[0])
        volatility = sum(abs(self._buf[i] - self._buf[i - 1]) for i in range(1, len(self._buf)))
        er = 0.0 if volatility == 0 else change / volatility
        fast_sc = 2 / (self.fast + 1)
        slow_sc = 2 / (self.slow + 1)
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        if math.isnan(self.current):
            return numeric
        return self.current + sc * (numeric - self.current)


# ---------------------------------------------------------------------------
# Oscillators
# ---------------------------------------------------------------------------


class RelativeStrengthIndex(IndicatorBase[float]):
    name = "RSI"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._prev: float = float("nan")
        self._avg_gain = 0.0
        self._avg_loss = 0.0

    def compute_next_value(self, _input: float, numeric: float) -> float:
        if math.isnan(self._prev):
            self._prev = numeric
            return float("nan")
        delta = numeric - self._prev
        self._prev = numeric
        gain = max(delta, 0.0)
        loss = abs(min(delta, 0.0))
        if self.samples <= self.period:
            self._avg_gain += gain / self.period
            self._avg_loss += loss / self.period
        else:
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period
        if self._avg_loss == 0:
            return 100.0
        rs = self._avg_gain / self._avg_loss
        return 100 - (100 / (1 + rs))


class MovingAverageConvergenceDivergence(IndicatorBase[float]):
    """MACD (line / signal / histogram)."""

    name = "MACD"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        super().__init__(period=slow)
        self.fast_ema = ExponentialMovingAverage(fast)
        self.slow_ema = ExponentialMovingAverage(slow)
        self.signal_ema = ExponentialMovingAverage(signal)
        self.histogram: float = float("nan")
        self.signal_value: float = float("nan")

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self.fast_ema.update(numeric)
        self.slow_ema.update(numeric)
        if math.isnan(self.fast_ema.current) or math.isnan(self.slow_ema.current):
            return float("nan")
        macd = self.fast_ema.current - self.slow_ema.current
        self.signal_ema.update(macd)
        self.signal_value = self.signal_ema.current
        if not math.isnan(self.signal_value):
            self.histogram = macd - self.signal_value
        return macd


class Stochastic(IndicatorBase[BarData]):
    """Fast stochastic %K and %D."""

    name = "Stochastic"

    def __init__(self, period: int = 14, smoothing: int = 3) -> None:
        super().__init__(period=period)
        self._buf: deque[BarData] = deque(maxlen=period)
        self._d_buf: deque[float] = deque(maxlen=smoothing)
        self.k_value: float = float("nan")
        self.d_value: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self._buf.append(input_value)
        if len(self._buf) < self.period:
            return float("nan")
        high = max(b.high for b in self._buf)
        low = min(b.low for b in self._buf)
        if high == low:
            self.k_value = 50.0
        else:
            self.k_value = 100 * (input_value.close - low) / (high - low)
        self._d_buf.append(self.k_value)
        self.d_value = sum(self._d_buf) / len(self._d_buf)
        return self.k_value


class CommodityChannelIndex(IndicatorBase[BarData]):
    name = "CCI"

    def __init__(self, period: int = 20) -> None:
        super().__init__(period=period)
        self._tp_buf: deque[float] = deque(maxlen=period)

    def _extract_value(self, value: BarData) -> float:
        return (value.high + value.low + value.close) / 3

    def compute_next_value(self, _input: BarData, numeric: float) -> float:
        self._tp_buf.append(numeric)
        if len(self._tp_buf) < self.period:
            return float("nan")
        mean = sum(self._tp_buf) / self.period
        mad = sum(abs(x - mean) for x in self._tp_buf) / self.period
        if mad == 0:
            return 0.0
        return (numeric - mean) / (0.015 * mad)


class WilliamsPercentR(IndicatorBase[BarData]):
    name = "WilliamsR"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._buf: deque[BarData] = deque(maxlen=period)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self._buf.append(input_value)
        if len(self._buf) < self.period:
            return float("nan")
        high = max(b.high for b in self._buf)
        low = min(b.low for b in self._buf)
        if high == low:
            return -50.0
        return -100 * (high - input_value.close) / (high - low)


class MoneyFlowIndex(IndicatorBase[BarData]):
    name = "MFI"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._pos: deque[float] = deque(maxlen=period)
        self._neg: deque[float] = deque(maxlen=period)
        self._prev_tp: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return (value.high + value.low + value.close) / 3

    def compute_next_value(self, input_value: BarData, numeric: float) -> float:
        raw_flow = numeric * input_value.volume
        if math.isnan(self._prev_tp):
            self._prev_tp = numeric
            self._pos.append(0.0)
            self._neg.append(0.0)
            return float("nan")
        if numeric > self._prev_tp:
            self._pos.append(raw_flow)
            self._neg.append(0.0)
        elif numeric < self._prev_tp:
            self._pos.append(0.0)
            self._neg.append(raw_flow)
        else:
            self._pos.append(0.0)
            self._neg.append(0.0)
        self._prev_tp = numeric
        if len(self._pos) < self.period:
            return float("nan")
        pos_sum = sum(self._pos)
        neg_sum = sum(self._neg)
        if neg_sum == 0:
            return 100.0
        ratio = pos_sum / neg_sum
        return 100 - (100 / (1 + ratio))


class UltimateOscillator(IndicatorBase[BarData]):
    name = "UO"

    def __init__(self, short: int = 7, medium: int = 14, long: int = 28) -> None:
        super().__init__(period=long)
        self.short = short
        self.medium = medium
        self.long = long
        self._bp: deque[float] = deque(maxlen=long)
        self._tr: deque[float] = deque(maxlen=long)
        self._prev_close: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        low_min = input_value.low if math.isnan(self._prev_close) else min(input_value.low, self._prev_close)
        high_max = input_value.high if math.isnan(self._prev_close) else max(input_value.high, self._prev_close)
        bp = input_value.close - low_min
        tr = high_max - low_min
        self._bp.append(bp)
        self._tr.append(tr)
        self._prev_close = input_value.close
        if len(self._bp) < self.long:
            return float("nan")

        def _avg(n: int) -> float:
            bp_sum = sum(list(self._bp)[-n:])
            tr_sum = sum(list(self._tr)[-n:])
            return bp_sum / tr_sum if tr_sum else 0.0

        return 100 * (4 * _avg(self.short) + 2 * _avg(self.medium) + _avg(self.long)) / 7


class AroonOscillator(IndicatorBase[BarData]):
    name = "Aroon"

    def __init__(self, period: int = 25) -> None:
        super().__init__(period=period)
        self._buf: deque[BarData] = deque(maxlen=period + 1)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self._buf.append(input_value)
        if len(self._buf) < self.period + 1:
            return float("nan")
        highs = [b.high for b in self._buf]
        lows = [b.low for b in self._buf]
        idx_high = self.period - highs[::-1].index(max(highs))
        idx_low = self.period - lows[::-1].index(min(lows))
        up = 100 * idx_high / self.period
        down = 100 * idx_low / self.period
        return up - down


class TRIX(IndicatorBase[float]):
    """1-period rate-of-change of a triple-smoothed EMA."""

    name = "TRIX"

    def __init__(self, period: int = 15) -> None:
        super().__init__(period=period)
        self._ema1 = ExponentialMovingAverage(period)
        self._ema2 = ExponentialMovingAverage(period)
        self._ema3 = ExponentialMovingAverage(period)
        self._prev_tema: float = float("nan")

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self._ema1.update(numeric)
        if math.isnan(self._ema1.current):
            return float("nan")
        self._ema2.update(self._ema1.current)
        if math.isnan(self._ema2.current):
            return float("nan")
        self._ema3.update(self._ema2.current)
        tema = self._ema3.current
        if math.isnan(tema) or math.isnan(self._prev_tema) or self._prev_tema == 0:
            self._prev_tema = tema
            return float("nan")
        result = 100 * (tema - self._prev_tema) / self._prev_tema
        self._prev_tema = tema
        return result


# ---------------------------------------------------------------------------
# Volatility / bands
# ---------------------------------------------------------------------------


class BollingerBands(IndicatorBase[float]):
    name = "BBands"

    def __init__(self, period: int = 20, k: float = 2.0) -> None:
        super().__init__(period=period)
        self.k = float(k)
        self._buf: deque[float] = deque(maxlen=period)
        self.upper: float = float("nan")
        self.middle: float = float("nan")
        self.lower: float = float("nan")

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self._buf.append(numeric)
        if len(self._buf) < self.period:
            return float("nan")
        mean = sum(self._buf) / self.period
        var = sum((x - mean) ** 2 for x in self._buf) / self.period
        std = math.sqrt(var)
        self.middle = mean
        self.upper = mean + self.k * std
        self.lower = mean - self.k * std
        return self.middle


class AverageTrueRange(IndicatorBase[BarData]):
    name = "ATR"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._prev_close: float = float("nan")
        self._tr_buf: deque[float] = deque(maxlen=period)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        high, low, close = input_value.high, input_value.low, input_value.close
        if math.isnan(self._prev_close):
            tr = high - low
        else:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        self._prev_close = close
        self._tr_buf.append(tr)
        if len(self._tr_buf) < self.period:
            return float("nan")
        return sum(self._tr_buf) / self.period


class KeltnerChannels(IndicatorBase[BarData]):
    name = "Keltner"

    def __init__(self, period: int = 20, multiplier: float = 2.0) -> None:
        super().__init__(period=period)
        self.multiplier = multiplier
        self.ema = ExponentialMovingAverage(period)
        self.atr = AverageTrueRange(period)
        self.upper: float = float("nan")
        self.middle: float = float("nan")
        self.lower: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self.ema.update(input_value.close)
        self.atr.update(input_value)
        if math.isnan(self.ema.current) or math.isnan(self.atr.current):
            return float("nan")
        self.middle = self.ema.current
        self.upper = self.ema.current + self.multiplier * self.atr.current
        self.lower = self.ema.current - self.multiplier * self.atr.current
        return self.middle


class DonchianChannel(IndicatorBase[BarData]):
    name = "Donchian"

    def __init__(self, period: int = 20) -> None:
        super().__init__(period=period)
        self._buf: deque[BarData] = deque(maxlen=period)
        self.upper: float = float("nan")
        self.middle: float = float("nan")
        self.lower: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self._buf.append(input_value)
        if len(self._buf) < self.period:
            return float("nan")
        self.upper = max(b.high for b in self._buf)
        self.lower = min(b.low for b in self._buf)
        self.middle = (self.upper + self.lower) / 2
        return self.middle


class ParabolicSAR(IndicatorBase[BarData]):
    name = "PSAR"

    def __init__(self, af_start: float = 0.02, af_step: float = 0.02, af_max: float = 0.2) -> None:
        super().__init__(period=2)
        self.af_start = af_start
        self.af_step = af_step
        self.af_max = af_max
        self._rising: bool = True
        self._af: float = af_start
        self._ep: float = float("nan")
        self._sar: float = float("nan")
        self._prev_bar: BarData | None = None

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        if self._prev_bar is None:
            self._prev_bar = input_value
            self._sar = input_value.low
            self._ep = input_value.high
            return self._sar
        self._sar = self._sar + self._af * (self._ep - self._sar)
        if self._rising:
            if input_value.low < self._sar:
                self._rising = False
                self._sar = self._ep
                self._ep = input_value.low
                self._af = self.af_start
            else:
                if input_value.high > self._ep:
                    self._ep = input_value.high
                    self._af = min(self._af + self.af_step, self.af_max)
        else:
            if input_value.high > self._sar:
                self._rising = True
                self._sar = self._ep
                self._ep = input_value.high
                self._af = self.af_start
            else:
                if input_value.low < self._ep:
                    self._ep = input_value.low
                    self._af = min(self._af + self.af_step, self.af_max)
        self._prev_bar = input_value
        return self._sar


# ---------------------------------------------------------------------------
# Trend strength
# ---------------------------------------------------------------------------


class AverageDirectionalIndex(IndicatorBase[BarData]):
    """ADX via smoothed +DI / -DI."""

    name = "ADX"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._prev_bar: BarData | None = None
        self._pdi: deque[float] = deque(maxlen=period)
        self._ndi: deque[float] = deque(maxlen=period)
        self._tr: deque[float] = deque(maxlen=period)
        self._adx_ema = ExponentialMovingAverage(period)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        if self._prev_bar is None:
            self._prev_bar = input_value
            return float("nan")
        prev = self._prev_bar
        up = input_value.high - prev.high
        down = prev.low - input_value.low
        plus_dm = up if up > down and up > 0 else 0.0
        minus_dm = down if down > up and down > 0 else 0.0
        tr = max(
            input_value.high - input_value.low,
            abs(input_value.high - prev.close),
            abs(input_value.low - prev.close),
        )
        self._pdi.append(plus_dm)
        self._ndi.append(minus_dm)
        self._tr.append(tr)
        self._prev_bar = input_value
        if len(self._tr) < self.period:
            return float("nan")
        atr = sum(self._tr)
        if atr == 0:
            return 0.0
        pdi = 100 * sum(self._pdi) / atr
        ndi = 100 * sum(self._ndi) / atr
        denom = pdi + ndi
        dx = 0.0 if denom == 0 else 100 * abs(pdi - ndi) / denom
        self._adx_ema.update(dx)
        return self._adx_ema.current


class ChaikinOscillator(IndicatorBase[BarData]):
    """Chaikin Oscillator = EMA3(AD) − EMA10(AD)."""

    name = "ChaikinOsc"

    def __init__(self, fast: int = 3, slow: int = 10) -> None:
        super().__init__(period=slow)
        self._ad: float = 0.0
        self._ema_fast = ExponentialMovingAverage(fast)
        self._ema_slow = ExponentialMovingAverage(slow)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        high, low, close, vol = (
            input_value.high,
            input_value.low,
            input_value.close,
            input_value.volume,
        )
        mf = 0.0 if high - low == 0 else (close - low - (high - close)) / (high - low)
        self._ad += mf * vol
        self._ema_fast.update(self._ad)
        self._ema_slow.update(self._ad)
        if math.isnan(self._ema_fast.current) or math.isnan(self._ema_slow.current):
            return float("nan")
        return self._ema_fast.current - self._ema_slow.current


class OnBalanceVolume(IndicatorBase[BarData]):
    name = "OBV"

    def __init__(self) -> None:
        super().__init__(period=1)
        self._prev_close: float = float("nan")
        self._obv: float = 0.0

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        if math.isnan(self._prev_close):
            self._prev_close = input_value.close
            return 0.0
        if input_value.close > self._prev_close:
            self._obv += input_value.volume
        elif input_value.close < self._prev_close:
            self._obv -= input_value.volume
        self._prev_close = input_value.close
        return self._obv


class VolumeWeightedAveragePrice(IndicatorBase[BarData]):
    """Rolling VWAP."""

    name = "VWAP"

    def __init__(self, period: int = 20) -> None:
        super().__init__(period=period)
        self._pv: deque[float] = deque(maxlen=period)
        self._v: deque[float] = deque(maxlen=period)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        tp = (input_value.high + input_value.low + input_value.close) / 3
        self._pv.append(tp * input_value.volume)
        self._v.append(input_value.volume)
        if len(self._pv) < self.period:
            return float("nan")
        vol_sum = sum(self._v)
        if vol_sum == 0:
            return float("nan")
        return sum(self._pv) / vol_sum


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class ZScore(IndicatorBase[float]):
    name = "Z"

    def __init__(self, period: int = 20) -> None:
        super().__init__(period=period)
        self._buf: deque[float] = deque(maxlen=period)

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self._buf.append(numeric)
        if len(self._buf) < self.period:
            return float("nan")
        mean = sum(self._buf) / self.period
        var = sum((x - mean) ** 2 for x in self._buf) / self.period
        std = math.sqrt(var)
        if std == 0:
            return 0.0
        return (numeric - mean) / std


class LogReturn(IndicatorBase[float]):
    name = "LogReturn"

    def __init__(self, period: int = 1) -> None:
        super().__init__(period=period)
        self._prev: float = float("nan")
        self._buf: deque[float] = deque(maxlen=period + 1)

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self._buf.append(numeric)
        if len(self._buf) < self.period + 1 or numeric <= 0:
            return float("nan")
        base = self._buf[0]
        if base <= 0:
            return float("nan")
        return math.log(numeric / base)


class RateOfChange(IndicatorBase[float]):
    name = "ROC"

    def __init__(self, period: int = 14) -> None:
        super().__init__(period=period)
        self._buf: deque[float] = deque(maxlen=period + 1)

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self._buf.append(numeric)
        if len(self._buf) < self.period + 1:
            return float("nan")
        base = self._buf[0]
        if base == 0:
            return float("nan")
        return 100 * (numeric - base) / base


class StandardDeviation(IndicatorBase[float]):
    name = "StdDev"

    def __init__(self, period: int = 20) -> None:
        super().__init__(period=period)
        self._buf: deque[float] = deque(maxlen=period)

    def compute_next_value(self, _input: float, numeric: float) -> float:
        self._buf.append(numeric)
        if len(self._buf) < self.period:
            return float("nan")
        mean = sum(self._buf) / self.period
        var = sum((x - mean) ** 2 for x in self._buf) / self.period
        return math.sqrt(var)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Extended indicator zoo (added in v0.4).
# ---------------------------------------------------------------------------


class Ichimoku(IndicatorBase[BarData]):
    """Ichimoku Kinko Hyo — returns the conversion-line (Tenkan-sen) value.

    The full five-line output is exposed as dataclass-like attributes
    (``tenkan``, ``kijun``, ``senkou_a``, ``senkou_b``, ``chikou``) mirroring
    the Lean implementation so downstream callers can read each line.
    """

    name = "Ichimoku"

    def __init__(
        self,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52,
    ) -> None:
        super().__init__(period=max(tenkan_period, kijun_period, senkou_b_period))
        self.tenkan_period = int(tenkan_period)
        self.kijun_period = int(kijun_period)
        self.senkou_b_period = int(senkou_b_period)
        self._highs: deque[float] = deque(maxlen=self.senkou_b_period)
        self._lows: deque[float] = deque(maxlen=self.senkou_b_period)
        self._closes: deque[float] = deque(maxlen=self.senkou_b_period)
        self.tenkan: float = float("nan")
        self.kijun: float = float("nan")
        self.senkou_a: float = float("nan")
        self.senkou_b: float = float("nan")
        self.chikou: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self._highs.append(input_value.high)
        self._lows.append(input_value.low)
        self._closes.append(input_value.close)
        if len(self._highs) < self.tenkan_period:
            return float("nan")
        tenkan_highs = list(self._highs)[-self.tenkan_period :]
        tenkan_lows = list(self._lows)[-self.tenkan_period :]
        self.tenkan = (max(tenkan_highs) + min(tenkan_lows)) / 2.0
        if len(self._highs) >= self.kijun_period:
            kijun_highs = list(self._highs)[-self.kijun_period :]
            kijun_lows = list(self._lows)[-self.kijun_period :]
            self.kijun = (max(kijun_highs) + min(kijun_lows)) / 2.0
        if not math.isnan(self.tenkan) and not math.isnan(self.kijun):
            self.senkou_a = (self.tenkan + self.kijun) / 2.0
        if len(self._highs) >= self.senkou_b_period:
            self.senkou_b = (max(self._highs) + min(self._lows)) / 2.0
        self.chikou = input_value.close
        return self.tenkan


class Supertrend(IndicatorBase[BarData]):
    """Supertrend trailing indicator over ATR bands."""

    name = "Supertrend"

    def __init__(self, period: int = 10, multiplier: float = 3.0) -> None:
        super().__init__(period=period)
        self.multiplier = float(multiplier)
        self.atr = AverageTrueRange(period)
        self._trend: int = 0  # +1 = up, -1 = down
        self._level: float = float("nan")
        self.upper: float = float("nan")
        self.lower: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self.atr.update(input_value)
        if math.isnan(self.atr.current):
            return float("nan")
        hl2 = (input_value.high + input_value.low) / 2.0
        upper = hl2 + self.multiplier * self.atr.current
        lower = hl2 - self.multiplier * self.atr.current
        self.upper = upper
        self.lower = lower
        close = input_value.close
        if math.isnan(self._level):
            self._trend = 1 if close >= hl2 else -1
            self._level = lower if self._trend == 1 else upper
        else:
            if self._trend == 1:
                self._level = max(self._level, lower)
                if close < self._level:
                    self._trend = -1
                    self._level = upper
            else:
                self._level = min(self._level, upper)
                if close > self._level:
                    self._trend = 1
                    self._level = lower
        return self._level


class PivotPoints(IndicatorBase[BarData]):
    """Classic floor-trader pivot points — emits the central pivot ``P``."""

    name = "Pivot"

    def __init__(self) -> None:
        super().__init__(period=1)
        self.r1: float = float("nan")
        self.r2: float = float("nan")
        self.s1: float = float("nan")
        self.s2: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        p = (input_value.high + input_value.low + input_value.close) / 3.0
        self.r1 = 2 * p - input_value.low
        self.s1 = 2 * p - input_value.high
        self.r2 = p + (input_value.high - input_value.low)
        self.s2 = p - (input_value.high - input_value.low)
        return p


class HeikinAshiTransform(IndicatorBase[BarData]):
    """Rolling Heikin-Ashi transform. ``current`` = HA close."""

    name = "HA"

    def __init__(self) -> None:
        super().__init__(period=1)
        self.ha_open: float = float("nan")
        self.ha_high: float = float("nan")
        self.ha_low: float = float("nan")

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        ha_close = (
            input_value.open + input_value.high + input_value.low + input_value.close
        ) / 4.0
        if math.isnan(self.ha_open):
            self.ha_open = (input_value.open + input_value.close) / 2.0
        else:
            # Previous HA_open and HA_close from state.
            self.ha_open = (self.ha_open + self.current) / 2.0 if not math.isnan(self.current) else self.ha_open
        self.ha_high = max(input_value.high, self.ha_open, ha_close)
        self.ha_low = min(input_value.low, self.ha_open, ha_close)
        return ha_close


class AroonUp(IndicatorBase[BarData]):
    """Aroon-Up component (percent of bars since the last rolling-high)."""

    name = "AroonUp"

    def __init__(self, period: int = 25) -> None:
        super().__init__(period=period)
        self._highs: deque[float] = deque(maxlen=period)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self._highs.append(input_value.high)
        if len(self._highs) < self.period:
            return float("nan")
        highs = list(self._highs)
        idx = int(len(highs) - 1 - highs.index(max(highs)))
        return 100.0 * (self.period - idx) / self.period


class AroonDown(IndicatorBase[BarData]):
    """Aroon-Down component."""

    name = "AroonDown"

    def __init__(self, period: int = 25) -> None:
        super().__init__(period=period)
        self._lows: deque[float] = deque(maxlen=period)

    def _extract_value(self, value: BarData) -> float:
        return value.close

    def compute_next_value(self, input_value: BarData, _numeric: float) -> float:
        self._lows.append(input_value.low)
        if len(self._lows) < self.period:
            return float("nan")
        lows = list(self._lows)
        idx = int(len(lows) - 1 - lows.index(min(lows)))
        return 100.0 * (self.period - idx) / self.period


# ---------------------------------------------------------------------------
# Indicator registry.
# ---------------------------------------------------------------------------


ALL_INDICATORS: dict[str, type[IndicatorBase]] = {
    "SMA": SimpleMovingAverage,
    "EMA": ExponentialMovingAverage,
    "HMA": HullMovingAverage,
    "KAMA": KAMA,
    "RSI": RelativeStrengthIndex,
    "MACD": MovingAverageConvergenceDivergence,
    "Stochastic": Stochastic,
    "CCI": CommodityChannelIndex,
    "WilliamsR": WilliamsPercentR,
    "MFI": MoneyFlowIndex,
    "UO": UltimateOscillator,
    "Aroon": AroonOscillator,
    "AroonUp": AroonUp,
    "AroonDown": AroonDown,
    "TRIX": TRIX,
    "BBands": BollingerBands,
    "ATR": AverageTrueRange,
    "Keltner": KeltnerChannels,
    "Donchian": DonchianChannel,
    "PSAR": ParabolicSAR,
    "ADX": AverageDirectionalIndex,
    "ChaikinOsc": ChaikinOscillator,
    "OBV": OnBalanceVolume,
    "VWAP": VolumeWeightedAveragePrice,
    "Z": ZScore,
    "LogReturn": LogReturn,
    "ROC": RateOfChange,
    "StdDev": StandardDeviation,
    # v0.4 extensions.
    "Ichimoku": Ichimoku,
    "Supertrend": Supertrend,
    "Pivot": PivotPoints,
    "HA": HeikinAshiTransform,
}


def build_indicator(name: str, **kwargs) -> IndicatorBase:
    """Instantiate an indicator by its short name."""
    cls = ALL_INDICATORS.get(name)
    if cls is None:
        raise KeyError(f"unknown indicator: {name!r}; known={sorted(ALL_INDICATORS)}")
    return cls(**kwargs)


def warmup(indicator: IndicatorBase, series: Iterable[float | BarData]) -> float:
    """Feed an iterable of values into an indicator; returns the final output."""
    result = float("nan")
    for v in series:
        result = indicator.update(v)
    return result
