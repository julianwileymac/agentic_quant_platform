"""Notebook-master strategy ports.

All strategies subclass :class:`aqp.strategies.qtradex.alphas.BasicAlphaBase`
to share the per-symbol generation pattern.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.data.cointegration import engle_granger
from aqp.data.realised_volatility import yang_zhang
from aqp.strategies.qtradex.alphas import BasicAlphaBase, _atr, _ema, _rsi, _sma

logger = logging.getLogger(__name__)


def _annualised_vol(close: pd.Series, window: int = 60) -> float:
    rets = np.log(close / close.shift(1)).dropna()
    if len(rets) < window:
        return float("nan")
    return float(rets.tail(window).std() * np.sqrt(252))


# ---------------------------------------------------------------------------
# Trend family
# ---------------------------------------------------------------------------


@register("MoskowitzTSMOMAlpha", source="notebooks", category="trend")
class MoskowitzTSMOMAlpha(BasicAlphaBase):
    """12-month TSMOM with vol scaling (Moskowitz 2012)."""

    name = "MoskowitzTSMOMAlpha"

    def __init__(self, lookback_months: int = 12, target_vol: float = 0.40, vol_window: int = 60, position_cap: float = 2.0) -> None:
        self.lookback_months = lookback_months
        self.target_vol = target_vol
        self.vol_window = vol_window
        self.position_cap = position_cap
        self.min_history = max(lookback_months * 21, vol_window)

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        lookback_bars = self.lookback_months * 21
        if len(close) < lookback_bars:
            return None
        ret_12m = close.iloc[-1] / close.iloc[-lookback_bars] - 1.0
        vol = _annualised_vol(close, self.vol_window)
        if pd.isna(vol) or vol <= 0:
            return None
        scale = min(self.target_vol / vol, self.position_cap)
        if ret_12m > 0:
            return 1, min(1.0, scale), f"+12m ret={ret_12m:.3f} vol={vol:.3f}"
        if ret_12m < 0:
            return -1, min(1.0, scale), f"-12m ret={ret_12m:.3f} vol={vol:.3f}"
        return None


@register("BaltasTrendAlpha", source="notebooks", category="trend")
class BaltasTrendAlpha(BasicAlphaBase):
    """Baltas 2020 TSMOM with Yang-Zhang vol estimator."""

    name = "BaltasTrendAlpha"

    def __init__(self, lookback_months: int = 12, target_vol: float = 0.20, vol_window: int = 30) -> None:
        self.lookback_months = lookback_months
        self.target_vol = target_vol
        self.vol_window = vol_window
        self.min_history = lookback_months * 21 + vol_window

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        lookback_bars = self.lookback_months * 21
        if len(close) < lookback_bars:
            return None
        ret = close.iloc[-1] / close.iloc[-lookback_bars] - 1.0
        yz = yang_zhang(sub["open"], sub["high"], sub["low"], close, period=self.vol_window).iloc[-1]
        if pd.isna(yz) or yz <= 0:
            return None
        scale = min(self.target_vol / yz, 2.0)
        sign = 1 if ret > 0 else -1
        return sign, min(1.0, scale), f"BaltasTrend ret={ret:.3f} yz={yz:.3f}"


@register("BreakoutTrendAlpha", source="notebooks", category="trend")
class BreakoutTrendAlpha(BasicAlphaBase):
    """N-period Donchian breakout filter atop TSMOM signal."""

    name = "BreakoutTrendAlpha"

    def __init__(self, lookback_bars: int = 252, breakout_bars: int = 55) -> None:
        self.lookback_bars = lookback_bars
        self.breakout_bars = breakout_bars
        self.min_history = lookback_bars

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        if len(close) < self.lookback_bars:
            return None
        ret = close.iloc[-1] / close.iloc[-self.lookback_bars] - 1.0
        donchian_high = sub["high"].rolling(self.breakout_bars).max().iloc[-1]
        donchian_low = sub["low"].rolling(self.breakout_bars).min().iloc[-1]
        last = close.iloc[-1]
        if ret > 0 and last >= donchian_high * 0.995:
            return 1, 0.7, f"breakout ret>0 high={donchian_high:.2f}"
        if ret < 0 and last <= donchian_low * 1.005:
            return -1, 0.7, f"breakdown ret<0 low={donchian_low:.2f}"
        return None


# ---------------------------------------------------------------------------
# FX / commodity factor family (cross-sectional)
# ---------------------------------------------------------------------------


@register("FXCarryAlpha", source="notebooks", category="carry")
class FXCarryAlpha(BasicAlphaBase):
    """FX carry — long high-yielders, short low-yielders.

    Reads carry rates from ``context["carry_rates"]`` (a ``{vt_symbol: rate}``
    mapping). Without that context, returns no signals.
    """

    name = "FXCarryAlpha"

    def __init__(self, top_quantile: float = 0.3) -> None:
        self.top_quantile = top_quantile
        self.min_history = 21

    def generate_signals(self, bars, universe, context):
        carry_rates: dict[str, float] = context.get("carry_rates", {})
        if not carry_rates:
            return []
        ranked = sorted(carry_rates.items(), key=lambda kv: kv[1], reverse=True)
        n = len(ranked)
        cutoff = max(1, int(n * self.top_quantile))
        signals = []
        from aqp.core.types import Direction, Signal, Symbol  # local import to avoid cycle
        for vt, _ in ranked[:cutoff]:
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt), strength=0.6, direction=Direction.LONG,
                    source=self.name, rationale="FX carry top",
                )
            )
        for vt, _ in ranked[-cutoff:]:
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt), strength=0.6, direction=Direction.SHORT,
                    source=self.name, rationale="FX carry bottom",
                )
            )
        return signals


def _cross_sectional_rank(values: dict[str, float]) -> dict[str, float]:
    """Return percentile rank in [0, 1]."""
    if not values:
        return {}
    sorted_items = sorted(values.items(), key=lambda kv: kv[1])
    n = len(sorted_items)
    return {k: i / max(n - 1, 1) for i, (k, _) in enumerate(sorted_items)}


class _CrossSectionalRankBase(BasicAlphaBase):
    """Base for cross-sectional rotation strategies.

    Subclasses implement :meth:`compute_metric(sub)` returning a single
    float per symbol. Top and bottom quantiles get long / short signals.
    """

    top_quantile: float = 0.3

    def compute_metric(self, sub: pd.DataFrame) -> float:
        raise NotImplementedError

    def generate_signals(self, bars, universe, context):
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        metrics: dict[str, float] = {}
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.min_history:
                continue
            try:
                m = self.compute_metric(sub)
            except Exception:  # noqa: BLE001
                continue
            if pd.notna(m):
                metrics[vt_symbol] = float(m)
        if not metrics:
            return []
        ranked = sorted(metrics.items(), key=lambda kv: kv[1])
        n = len(ranked)
        cutoff = max(1, int(n * self.top_quantile))
        from aqp.core.types import Direction, Signal, Symbol
        signals = []
        for vt, _ in ranked[-cutoff:]:
            signals.append(Signal(
                symbol=Symbol.parse(vt), strength=0.6, direction=Direction.LONG,
                source=self.name, rationale=f"{self.name} top",
            ))
        for vt, _ in ranked[:cutoff]:
            signals.append(Signal(
                symbol=Symbol.parse(vt), strength=0.6, direction=Direction.SHORT,
                source=self.name, rationale=f"{self.name} bottom",
            ))
        return signals


@register("CommodityTermStructureAlpha", source="notebooks", category="commodity_carry")
class CommodityTermStructureAlpha(_CrossSectionalRankBase):
    """Long backwardation / short contango, ranked by roll yield.

    Roll yield read from ``context["roll_yields"][vt_symbol]``.
    """

    name = "CommodityTermStructureAlpha"
    min_history = 21

    def compute_metric(self, sub: pd.DataFrame) -> float:
        return float("nan")  # uses context override

    def generate_signals(self, bars, universe, context):
        roll_yields = context.get("roll_yields", {})
        if not roll_yields:
            return []
        from aqp.core.types import Direction, Signal, Symbol
        ranked = sorted(roll_yields.items(), key=lambda kv: kv[1], reverse=True)
        n = len(ranked)
        cutoff = max(1, int(n * self.top_quantile))
        signals = []
        for vt, _ in ranked[:cutoff]:
            signals.append(Signal(symbol=Symbol.parse(vt), strength=0.6, direction=Direction.LONG, source=self.name, rationale="backwardation"))
        for vt, _ in ranked[-cutoff:]:
            signals.append(Signal(symbol=Symbol.parse(vt), strength=0.6, direction=Direction.SHORT, source=self.name, rationale="contango"))
        return signals


@register("CommodityMomentumAlpha", source="notebooks", category="commodity_momentum")
class CommodityMomentumAlpha(_CrossSectionalRankBase):
    """Cross-sectional 12-month momentum on commodities."""

    name = "CommodityMomentumAlpha"
    min_history = 252

    def __init__(self, lookback_bars: int = 252, top_quantile: float = 0.33) -> None:
        self.lookback_bars = lookback_bars
        self.top_quantile = top_quantile
        self.min_history = lookback_bars

    def compute_metric(self, sub):
        if len(sub) < self.lookback_bars:
            return float("nan")
        return sub["close"].iloc[-1] / sub["close"].iloc[-self.lookback_bars] - 1.0


@register("CommoditySkewnessAlpha", source="notebooks", category="commodity_skew")
class CommoditySkewnessAlpha(_CrossSectionalRankBase):
    """Cross-sectional skewness factor on commodity returns."""

    name = "CommoditySkewnessAlpha"
    min_history = 60

    def __init__(self, window: int = 60) -> None:
        self.window = window
        self.min_history = window
        self.top_quantile = 0.33

    def compute_metric(self, sub):
        rets = sub["close"].pct_change().tail(self.window).dropna()
        if len(rets) < self.window // 2:
            return float("nan")
        return -float(rets.skew())  # invert: long lowest skew


@register("CommodityIntraCurveAlpha", source="notebooks", category="commodity")
class CommodityIntraCurveAlpha(_CrossSectionalRankBase):
    """Along-curve momentum (front leg). Reads ``front_minus_back`` from context."""

    name = "CommodityIntraCurveAlpha"
    min_history = 21

    def compute_metric(self, sub):
        return float("nan")

    def generate_signals(self, bars, universe, context):
        intra = context.get("front_minus_back", {})
        if not intra:
            return []
        from aqp.core.types import Direction, Signal, Symbol
        ranked = sorted(intra.items(), key=lambda kv: kv[1], reverse=True)
        n = len(ranked)
        cutoff = max(1, int(n * self.top_quantile))
        return [
            Signal(symbol=Symbol.parse(v), strength=0.6, direction=Direction.LONG, source=self.name, rationale="intra_curve_top")
            for v, _ in ranked[:cutoff]
        ] + [
            Signal(symbol=Symbol.parse(v), strength=0.6, direction=Direction.SHORT, source=self.name, rationale="intra_curve_bottom")
            for v, _ in ranked[-cutoff:]
        ]


@register("CommodityBasisMomentumAlpha", source="notebooks", category="commodity")
class CommodityBasisMomentumAlpha(_CrossSectionalRankBase):
    """Boons-style basis momentum (front - back returns)."""

    name = "CommodityBasisMomentumAlpha"
    min_history = 60

    def __init__(self, lookback: int = 60) -> None:
        self.lookback = lookback
        self.min_history = lookback
        self.top_quantile = 0.3

    def compute_metric(self, sub):
        # In absence of explicit second-leg data, use OLS slope as proxy
        close = sub["close"].tail(self.lookback)
        if len(close) < self.lookback:
            return float("nan")
        x = np.arange(len(close))
        slope = float(np.polyfit(x, close.to_numpy(), 1)[0])
        return slope


@register("CommodityBasisReversalAlpha", source="notebooks", category="commodity")
class CommodityBasisReversalAlpha(_CrossSectionalRankBase):
    """Short-term basis mean reversion (Rossi 2025)."""

    name = "CommodityBasisReversalAlpha"
    min_history = 21

    def __init__(self, short_lookback: int = 5, long_lookback: int = 60) -> None:
        self.short_lookback = short_lookback
        self.long_lookback = long_lookback
        self.min_history = long_lookback
        self.top_quantile = 0.3

    def compute_metric(self, sub):
        close = sub["close"]
        short_ret = close.iloc[-1] / close.iloc[-self.short_lookback] - 1.0
        long_ret = close.iloc[-1] / close.iloc[-self.long_lookback] - 1.0
        # invert short-term to mean-revert
        return -short_ret + 0.0 * long_ret


@register("ChineseFuturesTrendAlpha", source="notebooks", category="trend")
class ChineseFuturesTrendAlpha(MoskowitzTSMOMAlpha):
    """TSMOM applied to Chinese-listed futures (Li/Zhang/Zhou 2017)."""

    name = "ChineseFuturesTrendAlpha"


@register("CrossAssetSkewnessAlpha", source="notebooks", category="cross_asset")
class CrossAssetSkewnessAlpha(CommoditySkewnessAlpha):
    """Cross-asset skewness factor across asset classes."""

    name = "CrossAssetSkewnessAlpha"


@register("OvernightReturnsAlpha", source="notebooks", category="anomaly")
class OvernightReturnsAlpha(BasicAlphaBase):
    """Long overnight (close→open) returns, short intraday.

    For daily bars approximates overnight = open[t] / close[t-1] - 1.
    """

    name = "OvernightReturnsAlpha"

    def __init__(self) -> None:
        self.min_history = 30

    def signal_for_symbol(self, sub, context):
        overnight = sub["open"] / sub["close"].shift(1) - 1.0
        if pd.isna(overnight.iloc[-1]):
            return None
        # average overnight return over last 21 bars determines bias
        avg = overnight.tail(21).mean()
        if avg > 0.0005:
            return 1, 0.5, f"avg overnight={avg:.4f}"
        if avg < -0.0005:
            return -1, 0.5, f"avg overnight={avg:.4f}"
        return None


# ---------------------------------------------------------------------------
# Connors short-term equity strategies
# ---------------------------------------------------------------------------


@register("ConnorsThreeDownStrategy", source="notebooks", category="connors")
class ConnorsThreeDownStrategy(BasicAlphaBase):
    """3 down days + close > SMA(200) → buy."""

    name = "ConnorsThreeDownStrategy"

    def __init__(self) -> None:
        self.min_history = 210

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        sma200 = _sma(close, 200).iloc[-1]
        if pd.isna(sma200):
            return None
        last3 = close.tail(4).diff().dropna()
        if (last3 < 0).all() and close.iloc[-1] > sma200:
            return 1, 0.6, "3 down days above SMA200"
        return None


@register("ConnorsTenDayLowsStrategy", source="notebooks", category="connors")
class ConnorsTenDayLowsStrategy(BasicAlphaBase):
    """New 10-day low + close > SMA(200) → buy."""

    name = "ConnorsTenDayLowsStrategy"

    def __init__(self) -> None:
        self.min_history = 210

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        sma200 = _sma(close, 200).iloc[-1]
        if pd.isna(sma200):
            return None
        if close.iloc[-1] == close.tail(10).min() and close.iloc[-1] > sma200:
            return 1, 0.6, "10-day low above SMA200"
        return None


@register("ConnorsDoubleSevensStrategy", source="notebooks", category="connors")
class ConnorsDoubleSevensStrategy(BasicAlphaBase):
    """'Double 7s': close < 7d low and SMA200 rising → buy."""

    name = "ConnorsDoubleSevensStrategy"

    def __init__(self) -> None:
        self.min_history = 210

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        sma200 = _sma(close, 200)
        if pd.isna(sma200.iloc[-1]) or pd.isna(sma200.iloc[-2]):
            return None
        sma_rising = sma200.iloc[-1] > sma200.iloc[-2]
        seven_low = close.tail(7).min()
        if close.iloc[-1] <= seven_low and sma_rising:
            return 1, 0.6, "double 7s, SMA200 rising"
        return None


@register("ConnorsMonthEndStrategy", source="notebooks", category="connors")
class ConnorsMonthEndStrategy(BasicAlphaBase):
    """Month-end timing + 200d MA filter."""

    name = "ConnorsMonthEndStrategy"

    def __init__(self) -> None:
        self.min_history = 210

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        sma200 = _sma(close, 200).iloc[-1]
        if pd.isna(sma200):
            return None
        last_ts = sub["timestamp"].iloc[-1]
        try:
            day = pd.Timestamp(last_ts).day
            if day >= 25 and close.iloc[-1] > sma200:
                return 1, 0.5, "month-end above SMA200"
        except Exception:  # noqa: BLE001
            return None
        return None


# ---------------------------------------------------------------------------
# Stat-arb spreads (CrushSpread / CrackSpread)
# ---------------------------------------------------------------------------


@register("CrushSpreadStatArbStrategy", source="notebooks", category="stat_arb")
class CrushSpreadStatArbStrategy(BasicAlphaBase):
    """Soybean crush spread mean reversion.

    Reads paired prices from ``context["spread_series"]`` (a pd.Series).
    Trades z-score reversion when |z| > 2.
    """

    name = "CrushSpreadStatArbStrategy"

    def __init__(self, z_window: int = 60, z_threshold: float = 2.0) -> None:
        self.z_window = z_window
        self.z_threshold = z_threshold
        self.min_history = 0

    def generate_signals(self, bars, universe, context):
        spread = context.get("spread_series")
        if spread is None or len(spread) < self.z_window:
            return []
        z = (spread - spread.rolling(self.z_window).mean()) / spread.rolling(self.z_window).std()
        last_z = z.iloc[-1]
        if pd.isna(last_z) or abs(last_z) < self.z_threshold:
            return []
        from aqp.core.types import Direction, Signal, Symbol
        # context tells us which legs to trade
        legs = context.get("spread_legs", {})
        if not legs:
            return []
        out = []
        sign = -1 if last_z > 0 else 1  # mean-revert
        for vt, weight in legs.items():
            direction = Direction.LONG if (sign * weight) > 0 else Direction.SHORT
            out.append(Signal(
                symbol=Symbol.parse(vt), strength=min(1.0, abs(last_z) / 3),
                direction=direction, source=self.name,
                rationale=f"crush z={last_z:.2f} sign={sign} leg={vt}",
            ))
        return out


@register("CrackSpreadStatArbStrategy", source="notebooks", category="stat_arb")
class CrackSpreadStatArbStrategy(CrushSpreadStatArbStrategy):
    """Petroleum 3-2-1 crack spread variant of crush stat arb."""

    name = "CrackSpreadStatArbStrategy"


# ---------------------------------------------------------------------------
# Gao 2018 — intraday momentum
# ---------------------------------------------------------------------------


@register("GaoIntradayMomentumStrategy", source="notebooks", category="intraday")
class GaoIntradayMomentumStrategy(BasicAlphaBase):
    """First-30min return predicts last-30min return.

    Expects intraday bars with ``timestamp`` covering trading hours.
    Uses the sign of the first-30min return to size the last-30min trade.
    """

    name = "GaoIntradayMomentumStrategy"

    def __init__(self, first_window_bars: int = 6, last_window_bars: int = 6) -> None:
        self.first_window_bars = first_window_bars
        self.last_window_bars = last_window_bars
        self.min_history = first_window_bars + last_window_bars + 1

    def signal_for_symbol(self, sub, context):
        if len(sub) < self.min_history:
            return None
        first_ret = sub["close"].iloc[self.first_window_bars - 1] / sub["close"].iloc[0] - 1.0
        if abs(first_ret) < 0.001:
            return None
        if first_ret > 0:
            return 1, min(1.0, abs(first_ret) * 50), f"intraday momentum first_ret={first_ret:.4f}"
        return -1, min(1.0, abs(first_ret) * 50), f"intraday reversal first_ret={first_ret:.4f}"
