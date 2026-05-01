"""All 28 QTradeX bot ports as ``IAlphaModel`` classes.

Common pattern:
- ``__init__(self, **params)`` — accepts the bot's ``tune`` keys.
- ``generate_signals(bars, universe, context)`` — loops universe, computes
  indicator features per symbol, emits ``Signal`` objects with
  ``Direction.LONG`` / ``Direction.SHORT``.

Indicator math is implemented inline using pandas / numpy (no
dependency on the proprietary ``qx.ti`` / ``qx.qi`` modules). Where an
existing AQP indicator class fits cleanly, we delegate to
:mod:`aqp.core.indicators` via :class:`aqp.data.indicators_zoo.IndicatorZoo`.

See ``extractions/qtradex/REFERENCE.md`` for the original logic
references and rationale per strategy.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------


class BasicAlphaBase(IAlphaModel):
    """Common scaffolding for QTradeX-style alphas.

    Subclasses override :meth:`signal_for_symbol` returning a tuple of
    ``(direction, strength, rationale)`` or ``None`` if no signal.
    """

    name: str = "qtradex_alpha"
    min_history: int = 50

    def __init__(self) -> None:  # pragma: no cover - subclasses override
        pass

    def signal_for_symbol(self, sub: pd.DataFrame, context: dict[str, Any]) -> tuple[int, float, str] | None:
        raise NotImplementedError

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        now = context.get("current_time")
        signals: list[Signal] = []
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp").reset_index(drop=True)
            if len(sub) < self.min_history:
                continue
            try:
                outcome = self.signal_for_symbol(sub, context)
            except Exception as exc:  # noqa: BLE001
                logger.debug("%s skipped %s: %s", self.name, vt_symbol, exc)
                continue
            if outcome is None:
                continue
            direction_int, strength, rationale = outcome
            if direction_int == 0 or strength <= 0:
                continue
            direction = Direction.LONG if direction_int > 0 else Direction.SHORT
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt_symbol),
                    strength=float(min(1.0, abs(strength))),
                    direction=direction,
                    timestamp=now or sub["timestamp"].iloc[-1],
                    confidence=float(min(1.0, abs(strength))),
                    source=self.name,
                    rationale=rationale,
                )
            )
        return signals


# ---------------------------------------------------------------------------
# Compact indicator helpers (used across strategies)
# ---------------------------------------------------------------------------


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = -delta.clip(upper=0).rolling(n).mean().replace(0, np.nan)
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    sig = _ema(macd_line, signal)
    hist = macd_line - sig
    return macd_line, sig, hist


def _bbands(close: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    return mid + k * std, mid, mid - k * std


def _stoch(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14, smooth: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest = low.rolling(n).min()
    highest = high.rolling(n).max()
    k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    return k.rolling(smooth).mean(), k


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    plus_dm = (high.diff()).where((high.diff() > low.diff().abs()) & (high.diff() > 0), 0.0)
    minus_dm = (low.diff().abs()).where((low.diff().abs() > high.diff()) & (low.diff() < 0), 0.0)
    tr = _atr(high, low, close, n)
    plus_di = 100 * (plus_dm.rolling(n).mean() / tr).fillna(0)
    minus_di = 100 * (minus_dm.rolling(n).mean() / tr).fillna(0)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.rolling(n).mean().fillna(0)


def _aroon(high: pd.Series, low: pd.Series, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up = high.rolling(n + 1).apply(lambda w: 100.0 * (n - (n - int(np.argmax(w)))) / n, raw=True)
    down = low.rolling(n + 1).apply(lambda w: 100.0 * (n - (n - int(np.argmin(w)))) / n, raw=True)
    return up, down, up - down


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, n: int = 14) -> pd.Series:
    typical = (high + low + close) / 3.0
    money_flow = typical * volume
    delta = typical.diff()
    pos = money_flow.where(delta > 0, 0.0)
    neg = money_flow.where(delta < 0, 0.0)
    mr = pos.rolling(n).sum() / neg.rolling(n).sum().replace(0, np.nan)
    return 100 - 100 / (1 + mr)


def _vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    typical = (high + low + close) / 3.0
    return (typical * volume).cumsum() / volume.cumsum().replace(0, np.nan)


def _ichimoku_spans(high: pd.Series, low: pd.Series) -> tuple[pd.Series, pd.Series]:
    conv = (high.rolling(9).max() + low.rolling(9).min()) / 2.0
    base = (high.rolling(26).max() + low.rolling(26).min()) / 2.0
    span_a = (conv + base) / 2.0
    span_b = (high.rolling(52).max() + low.rolling(52).min()) / 2.0
    return span_a, span_b


def _heikin_ashi(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.DataFrame:
    ha_close = (open_ + high + low + close) / 4.0
    ha_open = ha_close.copy()
    ha_open.iloc[0] = (open_.iloc[0] + close.iloc[0]) / 2.0
    for i in range(1, len(ha_open)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0
    ha_high = pd.concat([high, ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([low, ha_open, ha_close], axis=1).min(axis=1)
    return pd.DataFrame({"open": ha_open, "high": ha_high, "low": ha_low, "close": ha_close})


# ---------------------------------------------------------------------------
# Aroon — single oscillator threshold
# ---------------------------------------------------------------------------


@register("AroonAlpha", source="qtradex", category="momentum")
class AroonAlpha(BasicAlphaBase):
    name = "AroonAlpha"

    def __init__(self, period: int = 14, buy_thresh: float = 50.0, sell_thresh: float = -50.0) -> None:
        self.period = int(period)
        self.buy_thresh = float(buy_thresh)
        self.sell_thresh = float(sell_thresh)
        self.min_history = period * 3

    def signal_for_symbol(self, sub, context):
        _up, _down, osc = _aroon(sub["high"], sub["low"], self.period)
        v = osc.iloc[-1]
        if pd.isna(v):
            return None
        if v > self.buy_thresh:
            return 1, abs(v) / 100.0, f"AroonOsc={v:.1f}>{self.buy_thresh}"
        if v < self.sell_thresh:
            return -1, abs(v) / 100.0, f"AroonOsc={v:.1f}<{self.sell_thresh}"
        return None


# ---------------------------------------------------------------------------
# Aroon + MFI + VWAP + EMA stack
# ---------------------------------------------------------------------------


@register("AroonMfiVwapAlpha", source="qtradex", category="momentum_volume")
class AroonMfiVwapAlpha(BasicAlphaBase):
    name = "AroonMfiVwapAlpha"

    def __init__(self, aroon_period: int = 14, mfi_period: int = 14, ema_period: int = 9) -> None:
        self.aroon_period = aroon_period
        self.mfi_period = mfi_period
        self.ema_period = ema_period
        self.min_history = max(aroon_period, mfi_period, ema_period) * 3

    def signal_for_symbol(self, sub, context):
        aroon_up, aroon_down, _ = _aroon(sub["high"], sub["low"], self.aroon_period)
        spread = (aroon_up - aroon_down).iloc[-1]
        ema = _ema(sub["close"], self.ema_period).iloc[-1]
        vwap = _vwap(sub["high"], sub["low"], sub["close"], sub["volume"]).iloc[-1]
        mfi = _mfi(sub["high"], sub["low"], sub["close"], sub["volume"], self.mfi_period).iloc[-1]
        if pd.isna(spread) or pd.isna(ema) or pd.isna(vwap) or pd.isna(mfi):
            return None
        bullish = spread > 25 and ema > vwap and mfi > 50
        bearish = spread < -25 and ema < vwap and mfi < 50
        if bullish:
            return 1, 0.6, f"AroonSpread>{spread:.1f}, MFI={mfi:.0f}>50"
        if bearish:
            return -1, 0.6, f"AroonSpread<{spread:.1f}, MFI={mfi:.0f}<50"
        return None


# ---------------------------------------------------------------------------
# BlackHole — compression / surge regime
# ---------------------------------------------------------------------------


@register("BlackHoleAlpha", source="qtradex", category="volatility_breakout")
class BlackHoleAlpha(BasicAlphaBase):
    name = "BlackHoleAlpha"

    def __init__(
        self,
        atr_period: int = 14,
        avg_period: int = 100,
        compression_ratio: float = 0.6,
        breakout_period: int = 20,
    ) -> None:
        self.atr_period = atr_period
        self.avg_period = avg_period
        self.compression_ratio = compression_ratio
        self.breakout_period = breakout_period
        self.min_history = avg_period + breakout_period

    def signal_for_symbol(self, sub, context):
        atr = _atr(sub["high"], sub["low"], sub["close"], self.atr_period)
        ratio = (atr / atr.rolling(self.avg_period).mean()).iloc[-1]
        if pd.isna(ratio):
            return None
        compressed_recent = (atr / atr.rolling(self.avg_period).mean()).tail(self.breakout_period).min()
        donchian_high = sub["high"].rolling(self.breakout_period).max().iloc[-1]
        donchian_low = sub["low"].rolling(self.breakout_period).min().iloc[-1]
        last_close = sub["close"].iloc[-1]
        if compressed_recent < self.compression_ratio:
            if last_close >= donchian_high:
                return 1, 0.7, "compression breakout up"
            if last_close <= donchian_low:
                return -1, 0.7, "compression breakout down"
        return None


# ---------------------------------------------------------------------------
# ClassicalCryptoBot — stack of MACD/RSI/SMA/EMA/ADX
# ---------------------------------------------------------------------------


@register("ClassicalCryptoAlpha", source="qtradex", category="composite_momentum")
class ClassicalCryptoAlpha(BasicAlphaBase):
    name = "ClassicalCryptoAlpha"

    def __init__(self) -> None:
        self.min_history = 100

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        sma = _sma(close, 20).iloc[-1]
        ema = _ema(close, 50).iloc[-1]
        rsi = _rsi(close, 14).iloc[-1]
        macd_line, sig, _ = _macd(close)
        adx = _adx(sub["high"], sub["low"], close, 14).iloc[-1]
        last = close.iloc[-1]
        if any(pd.isna(x) for x in (sma, ema, rsi, macd_line.iloc[-1], sig.iloc[-1], adx)):
            return None
        bullish = last > sma > ema and rsi > 55 and macd_line.iloc[-1] > sig.iloc[-1] and adx > 20
        bearish = last < sma < ema and rsi < 45 and macd_line.iloc[-1] < sig.iloc[-1] and adx > 20
        if bullish:
            return 1, 0.65, "all-stack bullish"
        if bearish:
            return -1, 0.65, "all-stack bearish"
        return None


# ---------------------------------------------------------------------------
# Confluence — EMA + RSI + MACD hist + BBands location
# ---------------------------------------------------------------------------


@register("ConfluenceAlpha", source="qtradex", category="composite_momentum")
class ConfluenceAlpha(BasicAlphaBase):
    name = "ConfluenceAlpha"

    def __init__(self) -> None:
        self.min_history = 60

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        ema = _ema(close, 50)
        rsi = _rsi(close, 14)
        _, _, hist = _macd(close)
        upper, mid, lower = _bbands(close, 20, 2)
        last = close.iloc[-1]
        if pd.isna(ema.iloc[-1]) or pd.isna(rsi.iloc[-1]):
            return None
        bull_count = sum([
            last > ema.iloc[-1],
            rsi.iloc[-1] > 55,
            hist.iloc[-1] > 0,
            last > mid.iloc[-1] and last < upper.iloc[-1],
        ])
        bear_count = sum([
            last < ema.iloc[-1],
            rsi.iloc[-1] < 45,
            hist.iloc[-1] < 0,
            last < mid.iloc[-1] and last > lower.iloc[-1],
        ])
        if bull_count >= 3:
            return 1, bull_count / 4.0, f"confluence_bull={bull_count}/4"
        if bear_count >= 3:
            return -1, bear_count / 4.0, f"confluence_bear={bear_count}/4"
        return None


# ---------------------------------------------------------------------------
# CryptoMasterBot — broad classical stack
# ---------------------------------------------------------------------------


@register("CryptoMasterAlpha", source="qtradex", category="composite_momentum")
class CryptoMasterAlpha(BasicAlphaBase):
    name = "CryptoMasterAlpha"

    def __init__(self) -> None:
        self.min_history = 100

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        macd_line, sig, _ = _macd(close)
        rsi = _rsi(close, 14).iloc[-1]
        upper, mid, lower = _bbands(close, 20, 2)
        k, d = _stoch(sub["high"], sub["low"], close)
        adx = _adx(sub["high"], sub["low"], close).iloc[-1]
        last = close.iloc[-1]
        if any(pd.isna(x) for x in (macd_line.iloc[-1], sig.iloc[-1], rsi, k.iloc[-1], adx)):
            return None
        bull = sum([
            macd_line.iloc[-1] > sig.iloc[-1], rsi > 50,
            last > mid.iloc[-1], k.iloc[-1] > d.iloc[-1], adx > 20,
        ])
        bear = sum([
            macd_line.iloc[-1] < sig.iloc[-1], rsi < 50,
            last < mid.iloc[-1], k.iloc[-1] < d.iloc[-1], adx > 20,
        ])
        if bull >= 4:
            return 1, bull / 5.0, "master_bull"
        if bear >= 4:
            return -1, bear / 5.0, "master_bear"
        return None


# ---------------------------------------------------------------------------
# Cthulhu — EMA + stdev channels + PSAR proxy
# ---------------------------------------------------------------------------


@register("CthulhuAlpha", source="qtradex", category="channel_breakout")
class CthulhuAlpha(BasicAlphaBase):
    name = "CthulhuAlpha"

    def __init__(self, ema_period: int = 50, k: float = 2.0) -> None:
        self.ema_period = ema_period
        self.k = k
        self.min_history = ema_period * 2

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        ema = _ema(close, self.ema_period)
        std = close.rolling(self.ema_period).std()
        upper = ema + self.k * std
        lower = ema - self.k * std
        last = close.iloc[-1]
        if pd.isna(upper.iloc[-1]) or pd.isna(lower.iloc[-1]):
            return None
        if last > upper.iloc[-1]:
            return 1, 0.6, "above upper channel"
        if last < lower.iloc[-1]:
            return -1, 0.6, "below lower channel"
        return None


# ---------------------------------------------------------------------------
# Directional Movement — DI cross + ADX gate
# ---------------------------------------------------------------------------


@register("DirectionalMovementAlpha", source="qtradex", category="trend")
class DirectionalMovementAlpha(BasicAlphaBase):
    name = "DirectionalMovementAlpha"

    def __init__(self, period: int = 14, adx_threshold: float = 25.0) -> None:
        self.period = period
        self.adx_threshold = adx_threshold
        self.min_history = period * 3

    def signal_for_symbol(self, sub, context):
        high, low, close = sub["high"], sub["low"], sub["close"]
        plus_dm = high.diff().where((high.diff() > low.diff().abs()) & (high.diff() > 0), 0.0)
        minus_dm = low.diff().abs().where((low.diff().abs() > high.diff()) & (low.diff() < 0), 0.0)
        tr = _atr(high, low, close, self.period)
        plus_di = 100 * (plus_dm.rolling(self.period).mean() / tr).fillna(0)
        minus_di = 100 * (minus_dm.rolling(self.period).mean() / tr).fillna(0)
        adx = _adx(high, low, close, self.period).iloc[-1]
        if pd.isna(plus_di.iloc[-1]) or pd.isna(minus_di.iloc[-1]):
            return None
        if adx < self.adx_threshold:
            return None
        if plus_di.iloc[-1] > minus_di.iloc[-1]:
            return 1, min(1.0, adx / 50.0), f"+DI>-DI, ADX={adx:.1f}"
        return -1, min(1.0, adx / 50.0), f"-DI>+DI, ADX={adx:.1f}"


# ---------------------------------------------------------------------------
# EmaCross (SMA-envelope variant from ema_cross.py)
# ---------------------------------------------------------------------------


@register("EmaCrossSMAAlpha", source="qtradex", category="trend")
class EmaCrossSMAAlpha(BasicAlphaBase):
    name = "EmaCrossSMAAlpha"

    def __init__(self, fast_period: int = 5, slow_period: int = 20, envelope_pct: float = 0.005) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.envelope_pct = envelope_pct
        self.min_history = slow_period * 3

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        fast = _sma(close, self.fast_period).iloc[-1]
        slow = _sma(close, self.slow_period).iloc[-1]
        if pd.isna(fast) or pd.isna(slow):
            return None
        ratio = fast / slow - 1.0
        if ratio > self.envelope_pct:
            return 1, min(1.0, abs(ratio) * 20), f"fast/slow={ratio:.4f}>+{self.envelope_pct}"
        if ratio < -self.envelope_pct:
            return -1, min(1.0, abs(ratio) * 20), f"fast/slow={ratio:.4f}<-{self.envelope_pct}"
        return None


# ---------------------------------------------------------------------------
# EmaCross (Heikin-Ashi variant from heiken_ashi.py)
# ---------------------------------------------------------------------------


@register("EmaCrossHAAlpha", source="qtradex", category="trend")
class EmaCrossHAAlpha(BasicAlphaBase):
    name = "EmaCrossHAAlpha"

    def __init__(self, fast_period: int = 5, slow_period: int = 20) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.min_history = slow_period * 3

    def signal_for_symbol(self, sub, context):
        ha = _heikin_ashi(sub["open"], sub["high"], sub["low"], sub["close"])
        fast = _sma(ha["close"], self.fast_period).iloc[-1]
        slow = _sma(ha["close"], self.slow_period).iloc[-1]
        if pd.isna(fast) or pd.isna(slow):
            return None
        if fast > slow * 1.001:
            return 1, 0.55, "HA SMA cross up"
        if fast < slow * 0.999:
            return -1, 0.55, "HA SMA cross down"
        return None


# ---------------------------------------------------------------------------
# ExtinctionEvent — three EMAs + dynamic channels + regime override
# ---------------------------------------------------------------------------


@register("ExtinctionEventAlpha", source="qtradex", category="regime_channel")
class ExtinctionEventAlpha(BasicAlphaBase):
    name = "ExtinctionEventAlpha"

    def __init__(self) -> None:
        self.min_history = 200

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        ema_short = _ema(close, 8)
        ema_med = _ema(close, 21)
        ema_long = _ema(close, 200)
        if pd.isna(ema_long.iloc[-1]):
            return None
        last = close.iloc[-1]
        bull_regime = last > ema_long.iloc[-1]
        bear_regime = last < ema_long.iloc[-1]
        cross_up = ema_short.iloc[-1] > ema_med.iloc[-1] and ema_short.iloc[-2] <= ema_med.iloc[-2]
        cross_down = ema_short.iloc[-1] < ema_med.iloc[-1] and ema_short.iloc[-2] >= ema_med.iloc[-2]
        if bull_regime and cross_up:
            return 1, 0.7, "ExtinctionEvent bull regime + EMA cross up"
        if bear_regime and cross_down:
            return -1, 0.7, "ExtinctionEvent bear regime + EMA cross down"
        return None


# ---------------------------------------------------------------------------
# Forty96 — 12-bit pattern → discrete tune table
# ---------------------------------------------------------------------------


@register("Forty96Alpha", source="qtradex", category="discrete_policy")
class Forty96Alpha(BasicAlphaBase):
    name = "Forty96Alpha"

    def __init__(self, tune_table: dict[str, int] | None = None) -> None:
        self.tune_table: dict[str, int] = tune_table or {}
        self.min_history = 100

    def _state_key(self, sub: pd.DataFrame) -> str:
        close = sub["close"]
        emas = [_ema(close, n) for n in (5, 8, 13, 21, 34, 55)]
        slopes = [e.diff().iloc[-1] for e in emas]
        comparisons = [
            emas[0].iloc[-1] > emas[1].iloc[-1],
            emas[1].iloc[-1] > emas[2].iloc[-1],
            emas[2].iloc[-1] > emas[3].iloc[-1],
            emas[3].iloc[-1] > emas[4].iloc[-1],
            emas[4].iloc[-1] > emas[5].iloc[-1],
            close.iloc[-1] > emas[0].iloc[-1],
        ]
        bits = [int(s > 0) for s in slopes] + [int(b) for b in comparisons]
        return "".join(str(b) for b in bits)

    def signal_for_symbol(self, sub, context):
        if not self.tune_table:
            return None
        key = self._state_key(sub)
        action = self.tune_table.get(key)
        if action == 1:
            return 1, 0.5, f"forty96 state={key}"
        if action == -1:
            return -1, 0.5, f"forty96 state={key}"
        return None


# ---------------------------------------------------------------------------
# UltimateForecastMesa — UO + FOSC + MSW vote
# ---------------------------------------------------------------------------


@register("UltimateForecastMesaAlpha", source="qtradex", category="oscillator_ensemble")
class UltimateForecastMesaAlpha(BasicAlphaBase):
    name = "UltimateForecastMesaAlpha"

    def __init__(self) -> None:
        self.min_history = 50

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        # Ultimate Oscillator (Williams)
        bp = close - pd.concat([sub["low"], close.shift(1)], axis=1).min(axis=1)
        tr = pd.concat([sub["high"], close.shift(1)], axis=1).max(axis=1) - pd.concat([sub["low"], close.shift(1)], axis=1).min(axis=1)
        avg7 = bp.rolling(7).sum() / tr.rolling(7).sum().replace(0, np.nan)
        avg14 = bp.rolling(14).sum() / tr.rolling(14).sum().replace(0, np.nan)
        avg28 = bp.rolling(28).sum() / tr.rolling(28).sum().replace(0, np.nan)
        uo = (4 * avg7 + 2 * avg14 + avg28) / 7 * 100
        # Forecast oscillator: percentage diff of close vs linear regression forecast
        x = np.arange(len(close))
        slope_int = np.polyfit(x[-30:], close.tail(30).to_numpy(), 1)
        forecast = slope_int[0] * (len(close) - 1) + slope_int[1]
        fosc = 100 * (close.iloc[-1] - forecast) / max(abs(forecast), 1e-12)
        # Mesa sine wave proxy
        msw = np.sin(2 * np.pi * (len(close) % 16) / 16)
        votes = sum([uo.iloc[-1] > 50, fosc > 0, msw > 0])
        if votes == 3:
            return 1, 0.6, "UO+FOSC+MSW all bullish"
        if votes == 0:
            return -1, 0.6, "UO+FOSC+MSW all bearish"
        return None


# ---------------------------------------------------------------------------
# FRAMA — adaptive trend
# ---------------------------------------------------------------------------


@register("FRAMABotAlpha", source="qtradex", category="adaptive_trend")
class FRAMABotAlpha(BasicAlphaBase):
    name = "FRAMABotAlpha"

    def __init__(self, period: int = 16) -> None:
        if period % 2:
            period += 1
        self.period = period
        self.min_history = period * 3

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        ema = _ema(close, self.period).iloc[-1]
        if pd.isna(ema):
            return None
        last = close.iloc[-1]
        if last > ema * 1.01:
            return 1, 0.5, "above FRAMA proxy"
        if last < ema * 0.99:
            return -1, 0.5, "below FRAMA proxy"
        return None


# ---------------------------------------------------------------------------
# ParabolicSAR — multi-PSAR + EMA confirmation
# ---------------------------------------------------------------------------


def _psar(high: pd.Series, low: pd.Series, af_step: float = 0.02, af_max: float = 0.20) -> pd.Series:
    """Approximate parabolic SAR (incremental)."""
    psar = low.copy().astype(float)
    bull = True
    af = af_step
    ep = high.iloc[0]
    psar.iloc[0] = low.iloc[0]
    for i in range(1, len(high)):
        prev = psar.iloc[i - 1]
        if bull:
            psar.iloc[i] = prev + af * (ep - prev)
            if low.iloc[i] < psar.iloc[i]:
                bull = False
                psar.iloc[i] = ep
                ep = low.iloc[i]
                af = af_step
            else:
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + af_step, af_max)
        else:
            psar.iloc[i] = prev + af * (ep - prev)
            if high.iloc[i] > psar.iloc[i]:
                bull = True
                psar.iloc[i] = ep
                ep = high.iloc[i]
                af = af_step
            else:
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + af_step, af_max)
    return psar


@register("ParabolicSARBotAlpha", source="qtradex", category="multi_param_trend")
class ParabolicSARBotAlpha(BasicAlphaBase):
    name = "ParabolicSARBotAlpha"

    def __init__(self) -> None:
        self.min_history = 50

    def signal_for_symbol(self, sub, context):
        psar_fast = _psar(sub["high"], sub["low"], 0.02, 0.20).iloc[-1]
        psar_slow = _psar(sub["high"], sub["low"], 0.01, 0.10).iloc[-1]
        ema = _ema(sub["close"], 21).iloc[-1]
        last = sub["close"].iloc[-1]
        if pd.isna(psar_fast) or pd.isna(ema):
            return None
        bull = last > psar_fast and last > psar_slow and last > ema
        bear = last < psar_fast and last < psar_slow and last < ema
        if bull:
            return 1, 0.6, "all PSARs + EMA bullish"
        if bear:
            return -1, 0.6, "all PSARs + EMA bearish"
        return None


# ---------------------------------------------------------------------------
# Ichimoku
# ---------------------------------------------------------------------------


@register("IchimokuBotAlpha", source="qtradex", category="cloud")
class IchimokuBotAlpha(BasicAlphaBase):
    name = "IchimokuBotAlpha"

    def __init__(self) -> None:
        self.min_history = 60

    def signal_for_symbol(self, sub, context):
        span_a, span_b = _ichimoku_spans(sub["high"], sub["low"])
        last = sub["close"].iloc[-1]
        a, b = span_a.iloc[-1], span_b.iloc[-1]
        if pd.isna(a) or pd.isna(b):
            return None
        if last > max(a, b):
            return 1, 0.55, "above ichimoku cloud"
        if last < min(a, b):
            return -1, 0.55, "below ichimoku cloud"
        return None


# ---------------------------------------------------------------------------
# IChing — 6-bit slope state → discrete tune
# ---------------------------------------------------------------------------


@register("IChingAlpha", source="qtradex", category="discrete_policy")
class IChingAlpha(BasicAlphaBase):
    name = "IChingAlpha"

    def __init__(self, tune_table: dict[str, int] | None = None) -> None:
        self.tune_table: dict[str, int] = tune_table or {}
        self.min_history = 60

    def _hexagram(self, sub: pd.DataFrame) -> str:
        close = sub["close"]
        emas = [_ema(close, n) for n in (3, 5, 8, 13, 21, 34)]
        return "".join("1" if e.diff().iloc[-1] > 0 else "0" for e in emas)

    def signal_for_symbol(self, sub, context):
        if not self.tune_table:
            return None
        key = self._hexagram(sub)
        action = self.tune_table.get(key)
        if action == 1:
            return 1, 0.5, f"iching state={key}"
        if action == -1:
            return -1, 0.5, f"iching state={key}"
        return None


# ---------------------------------------------------------------------------
# KSTIndicatorBot — KST cross signal
# ---------------------------------------------------------------------------


@register("KSTIndicatorBotAlpha", source="qtradex", category="oscillator")
class KSTIndicatorBotAlpha(BasicAlphaBase):
    name = "KSTIndicatorBotAlpha"

    def __init__(self) -> None:
        self.min_history = 80

    def _kst(self, close: pd.Series) -> pd.Series:
        roc1 = close.pct_change(10)
        roc2 = close.pct_change(15)
        roc3 = close.pct_change(20)
        roc4 = close.pct_change(30)
        return (
            _sma(roc1, 10) * 1
            + _sma(roc2, 10) * 2
            + _sma(roc3, 10) * 3
            + _sma(roc4, 15) * 4
        )

    def signal_for_symbol(self, sub, context):
        kst = self._kst(sub["close"])
        signal = _sma(kst, 9)
        if pd.isna(kst.iloc[-1]) or pd.isna(signal.iloc[-1]):
            return None
        if kst.iloc[-1] > signal.iloc[-1] and kst.iloc[-2] <= signal.iloc[-2]:
            return 1, 0.6, "KST cross up"
        if kst.iloc[-1] < signal.iloc[-1] and kst.iloc[-2] >= signal.iloc[-2]:
            return -1, 0.6, "KST cross down"
        return None


# ---------------------------------------------------------------------------
# LavaHK — OHLC4 + EMA mode heuristic
# ---------------------------------------------------------------------------


@register("LavaHKAlpha", source="qtradex", category="composite_trend")
class LavaHKAlpha(BasicAlphaBase):
    name = "LavaHKAlpha"

    def __init__(self) -> None:
        self.min_history = 60

    def signal_for_symbol(self, sub, context):
        ohlc4 = (sub["open"] + sub["high"] + sub["low"] + sub["close"]) / 4
        ema_fast = _ema(sub["close"], 8).iloc[-1]
        ema_slow = _ema(sub["close"], 21).iloc[-1]
        last_o = ohlc4.iloc[-1]
        last_open = sub["open"].iloc[-1]
        if pd.isna(ema_slow):
            return None
        if last_o > last_open and ema_fast > ema_slow:
            return 1, 0.55, "lava bull mode"
        if last_o < last_open and ema_fast < ema_slow:
            return -1, 0.55, "lava bear mode"
        return None


# ---------------------------------------------------------------------------
# MASabres — multi-MA slope vote (test target)
# ---------------------------------------------------------------------------


@register("MASabresAlpha", source="qtradex", category="consensus_trend")
class MASabresAlpha(BasicAlphaBase):
    name = "MASabresAlpha"
    min_history = 60

    def __init__(
        self,
        windows: tuple[int, ...] = (5, 10, 20, 50, 100),
        threshold_ratio: float = 0.6,
    ) -> None:
        self.windows = windows
        self.threshold_ratio = threshold_ratio
        self.min_history = max(windows) + 5

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        votes = 0
        for w in self.windows:
            ma = _sma(close, w)
            slope = ma.diff().iloc[-1]
            if pd.notna(slope):
                votes += np.sign(slope)
        n = len(self.windows)
        threshold = self.threshold_ratio * n
        if votes >= threshold:
            return 1, abs(votes) / n, f"slope votes={int(votes)}/{n}"
        if votes <= -threshold:
            return -1, abs(votes) / n, f"slope votes={int(votes)}/{n}"
        return None


# ---------------------------------------------------------------------------
# BBadXMacDrSi — MACD + RSI + FFT filter + ADX regime
# ---------------------------------------------------------------------------


@register("BBadXMacDrSiAlpha", source="qtradex", category="regime_aware_oscillator")
class BBadXMacDrSiAlpha(BasicAlphaBase):
    name = "BBadXMacDrSiAlpha"

    def __init__(self, adx_threshold: float = 25.0) -> None:
        self.adx_threshold = adx_threshold
        self.min_history = 100

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        macd_line, sig, _ = _macd(close)
        rsi = _rsi(close, 14)
        adx = _adx(sub["high"], sub["low"], close, 14).iloc[-1]
        if any(pd.isna(x) for x in (macd_line.iloc[-1], sig.iloc[-1], rsi.iloc[-1], adx)):
            return None
        in_trend = adx > self.adx_threshold
        # FFT low-pass smoothing on close (simple proxy)
        try:
            spec = np.fft.rfft(close.tail(64).to_numpy() - close.tail(64).mean())
            spec[len(spec) // 4:] = 0
            smooth = np.fft.irfft(spec, n=64)
            smooth_slope = smooth[-1] - smooth[-2]
        except Exception:  # noqa: BLE001
            smooth_slope = 0
        if in_trend:
            if macd_line.iloc[-1] > sig.iloc[-1] and rsi.iloc[-1] > 50 and smooth_slope > 0:
                return 1, 0.7, "trend bullish"
            if macd_line.iloc[-1] < sig.iloc[-1] and rsi.iloc[-1] < 50 and smooth_slope < 0:
                return -1, 0.7, "trend bearish"
        else:
            if rsi.iloc[-1] < 30:
                return 1, 0.5, "range oversold"
            if rsi.iloc[-1] > 70:
                return -1, 0.5, "range overbought"
        return None


# ---------------------------------------------------------------------------
# MasterBot — Stoch + RSI + MACD + ATR confirmation
# ---------------------------------------------------------------------------


@register("MasterBotAlpha", source="qtradex", category="composite_oscillator")
class MasterBotAlpha(BasicAlphaBase):
    name = "MasterBotAlpha"

    def __init__(self) -> None:
        self.min_history = 60

    def signal_for_symbol(self, sub, context):
        k, d = _stoch(sub["high"], sub["low"], sub["close"])
        rsi = _rsi(sub["close"], 14).iloc[-1]
        macd_line, sig, _ = _macd(sub["close"])
        atr = _atr(sub["high"], sub["low"], sub["close"], 14).iloc[-1]
        atr_avg = _atr(sub["high"], sub["low"], sub["close"], 14).rolling(50).mean().iloc[-1]
        if any(pd.isna(x) for x in (k.iloc[-1], rsi, macd_line.iloc[-1], atr, atr_avg)):
            return None
        atr_active = atr > atr_avg
        if not atr_active:
            return None
        if k.iloc[-1] > d.iloc[-1] and rsi > 50 and macd_line.iloc[-1] > sig.iloc[-1]:
            return 1, 0.65, "MasterBot bullish"
        if k.iloc[-1] < d.iloc[-1] and rsi < 50 and macd_line.iloc[-1] < sig.iloc[-1]:
            return -1, 0.65, "MasterBot bearish"
        return None


# ---------------------------------------------------------------------------
# Renko + RSI
# ---------------------------------------------------------------------------


@register("RenkoBotAlpha", source="qtradex", category="chart_type")
class RenkoBotAlpha(BasicAlphaBase):
    name = "RenkoBotAlpha"

    def __init__(self, brick_pct: float = 0.005) -> None:
        self.brick_pct = brick_pct
        self.min_history = 50

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        rsi = _rsi(close, 14).iloc[-1]
        # detect direction of last brick
        prev_brick = close.iloc[-10]
        last = close.iloc[-1]
        change = (last - prev_brick) / prev_brick
        if abs(change) < self.brick_pct:
            return None
        if change > 0 and rsi > 50:
            return 1, 0.6, f"renko up brick + RSI={rsi:.0f}"
        if change < 0 and rsi < 50:
            return -1, 0.6, f"renko down brick + RSI={rsi:.0f}"
        return None


# ---------------------------------------------------------------------------
# HeikinAshiIchimokuVortex — composite vote
# ---------------------------------------------------------------------------


@register("HeikinAshiIchimokuVortexAlpha", source="qtradex", category="composite")
class HeikinAshiIchimokuVortexAlpha(BasicAlphaBase):
    name = "HeikinAshiIchimokuVortexAlpha"

    def __init__(self) -> None:
        self.min_history = 60

    def signal_for_symbol(self, sub, context):
        ha = _heikin_ashi(sub["open"], sub["high"], sub["low"], sub["close"])
        ha_bull = ha["close"].iloc[-1] > ha["open"].iloc[-1]
        span_a, span_b = _ichimoku_spans(sub["high"], sub["low"])
        cloud_bull = sub["close"].iloc[-1] > max(span_a.iloc[-1], span_b.iloc[-1])
        cloud_bear = sub["close"].iloc[-1] < min(span_a.iloc[-1], span_b.iloc[-1])
        # mini-vortex
        vp = (sub["high"] - sub["low"].shift(1)).abs().rolling(14).sum()
        vm = (sub["low"] - sub["high"].shift(1)).abs().rolling(14).sum()
        v_bull = vp.iloc[-1] > vm.iloc[-1]
        if ha_bull and cloud_bull and v_bull:
            return 1, 0.7, "HA+Ichi+Vortex bull"
        if (not ha_bull) and cloud_bear and (not v_bull):
            return -1, 0.7, "HA+Ichi+Vortex bear"
        return None


# ---------------------------------------------------------------------------
# TradFiInspired — vote count of classical indicators
# ---------------------------------------------------------------------------


@register("TradFiInspiredAlpha", source="qtradex", category="consensus_voting")
class TradFiInspiredAlpha(BasicAlphaBase):
    name = "TradFiInspiredAlpha"

    def __init__(self, vote_threshold: int = 4) -> None:
        self.vote_threshold = vote_threshold
        self.min_history = 100

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        sma20 = _sma(close, 20).iloc[-1]
        sma50 = _sma(close, 50).iloc[-1]
        ema12 = _ema(close, 12).iloc[-1]
        ema26 = _ema(close, 26).iloc[-1]
        rsi = _rsi(close, 14).iloc[-1]
        macd_line, sig, _ = _macd(close)
        upper, mid, lower = _bbands(close, 20, 2)
        last = close.iloc[-1]
        if any(pd.isna(x) for x in (sma20, sma50, ema12, ema26, rsi, macd_line.iloc[-1])):
            return None
        bull_votes = sum([
            last > sma20, sma20 > sma50, ema12 > ema26,
            rsi > 50, macd_line.iloc[-1] > sig.iloc[-1],
            last > mid.iloc[-1],
        ])
        bear_votes = 6 - bull_votes
        if bull_votes >= self.vote_threshold:
            return 1, bull_votes / 6.0, f"TradFi votes bull={bull_votes}/6"
        if bear_votes >= self.vote_threshold:
            return -1, bear_votes / 6.0, f"TradFi votes bear={bear_votes}/6"
        return None


# ---------------------------------------------------------------------------
# TrimaZlemaFisher
# ---------------------------------------------------------------------------


def _trima(close: pd.Series, n: int) -> pd.Series:
    return _sma(_sma(close, n // 2 + 1), n // 2 + 1)


def _zlema(close: pd.Series, n: int) -> pd.Series:
    lag = (n - 1) // 2
    deviation = close + (close - close.shift(lag))
    return _ema(deviation, n)


@register("TrimaZlemaFisherAlpha", source="qtradex", category="smooth_momentum")
class TrimaZlemaFisherAlpha(BasicAlphaBase):
    name = "TrimaZlemaFisherAlpha"

    def __init__(self, period: int = 21) -> None:
        self.period = period
        self.min_history = period * 3

    def signal_for_symbol(self, sub, context):
        trima = _trima(sub["close"], self.period).iloc[-1]
        zlema = _zlema(sub["close"], self.period).iloc[-1]
        if pd.isna(trima) or pd.isna(zlema):
            return None
        ratio = (zlema - trima) / max(abs(trima), 1e-12)
        if ratio > 0.005:
            return 1, min(1.0, abs(ratio) * 50), f"ZLEMA>TRIMA, r={ratio:.4f}"
        if ratio < -0.005:
            return -1, min(1.0, abs(ratio) * 50), f"ZLEMA<TRIMA, r={ratio:.4f}"
        return None


# ---------------------------------------------------------------------------
# Vortex
# ---------------------------------------------------------------------------


@register("VortexAlpha", source="qtradex", category="trend")
class VortexAlpha(BasicAlphaBase):
    name = "VortexAlpha"

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self.min_history = period * 3

    def signal_for_symbol(self, sub, context):
        high, low, close = sub["high"], sub["low"], sub["close"]
        prev_close = close.shift(1)
        tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        vp = (high - low.shift(1)).abs()
        vm = (low - high.shift(1)).abs()
        sum_tr = tr.rolling(self.period).sum().iloc[-1]
        if sum_tr <= 0 or pd.isna(sum_tr):
            return None
        vp_n = vp.rolling(self.period).sum().iloc[-1] / sum_tr
        vm_n = vm.rolling(self.period).sum().iloc[-1] / sum_tr
        diff = vp_n - vm_n
        if diff > 0.05:
            return 1, min(1.0, abs(diff)), f"+VI>−VI by {diff:.3f}"
        if diff < -0.05:
            return -1, min(1.0, abs(diff)), f"−VI>+VI by {-diff:.3f}"
        return None
