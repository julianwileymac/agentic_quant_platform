"""TA-Lib indicator catalog with engine fallback (talib → pandas-ta-classic).

This module exposes the full TA-Lib taxonomy (Overlap, Momentum, Volume,
Volatility, Cycle, Pattern Recognition, Statistic, Math Transform, Math
Operator, Price Transform) as a metadata-driven catalog so the Web UI can
render every indicator regardless of which compute engine is installed.

Compute precedence:

1. ``talib`` (C-FFI) when importable — exact TA-Lib semantics.
2. ``pandas_ta_classic`` (or ``pandas_ta``) — pure-Python fallback that
   supplies the great majority of TA-Lib equivalents.
3. The native :mod:`aqp.core.indicators` zoo for indicators we already
   ship in-process.

If none of the above can compute a particular function, it stays in the
catalog (so the UI can show it) but ``can_compute`` is ``False``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine probes
# ---------------------------------------------------------------------------


def _probe_talib() -> Any | None:
    try:
        import talib  # type: ignore[import-not-found]

        return talib
    except Exception:  # pragma: no cover - talib often missing
        return None


def _probe_pandas_ta() -> Any | None:
    try:
        import pandas_ta as pta  # type: ignore[import-not-found]

        return pta
    except Exception:
        try:
            import pandas_ta_classic as pta  # type: ignore[import-not-found]

            return pta
        except Exception:
            return None


_TALIB = _probe_talib()
_PANDAS_TA = _probe_pandas_ta()


def engine_status() -> dict[str, bool]:
    return {
        "talib": _TALIB is not None,
        "pandas_ta": _PANDAS_TA is not None,
    }


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@dataclass
class IndicatorParam:
    name: str
    default: Any = None
    type: str = "int"  # int | float | str
    description: str = ""


@dataclass
class TalibIndicator:
    """Catalog entry for a single TA-Lib function."""

    name: str  # short id, e.g. "SMA"
    group: str  # e.g. "Overlap Studies"
    description: str = ""
    inputs: tuple[str, ...] = ("close",)
    outputs: tuple[str, ...] = ("value",)
    params: list[IndicatorParam] = field(default_factory=list)
    pandas_ta_kind: str | None = None  # method name on `df.ta`
    native_class: str | None = None  # ALL_INDICATORS key


# Static taxonomy. Curated and grouped to match TA-Lib's canonical groups.
# Each entry tells us how to compute via talib (function name = key),
# pandas-ta (`pandas_ta_kind`), or our native zoo (`native_class`).

_OVERLAP: list[TalibIndicator] = [
    TalibIndicator("SMA", "Overlap Studies", "Simple Moving Average",
        params=[IndicatorParam("timeperiod", 30, "int", "Lookback period")],
        pandas_ta_kind="sma", native_class="SMA"),
    TalibIndicator("EMA", "Overlap Studies", "Exponential Moving Average",
        params=[IndicatorParam("timeperiod", 30, "int", "Lookback period")],
        pandas_ta_kind="ema", native_class="EMA"),
    TalibIndicator("WMA", "Overlap Studies", "Weighted Moving Average",
        params=[IndicatorParam("timeperiod", 30, "int")],
        pandas_ta_kind="wma"),
    TalibIndicator("DEMA", "Overlap Studies", "Double Exponential Moving Average",
        params=[IndicatorParam("timeperiod", 30, "int")],
        pandas_ta_kind="dema"),
    TalibIndicator("TEMA", "Overlap Studies", "Triple Exponential Moving Average",
        params=[IndicatorParam("timeperiod", 30, "int")],
        pandas_ta_kind="tema"),
    TalibIndicator("TRIMA", "Overlap Studies", "Triangular Moving Average",
        params=[IndicatorParam("timeperiod", 30, "int")],
        pandas_ta_kind="trima"),
    TalibIndicator("KAMA", "Overlap Studies", "Kaufman Adaptive Moving Average",
        params=[IndicatorParam("timeperiod", 30, "int")],
        pandas_ta_kind="kama", native_class="KAMA"),
    TalibIndicator("MAMA", "Overlap Studies", "MESA Adaptive Moving Average",
        params=[IndicatorParam("fastlimit", 0.5, "float"),
                IndicatorParam("slowlimit", 0.05, "float")],
        outputs=("mama", "fama")),
    TalibIndicator("T3", "Overlap Studies", "Triple Exponential Moving Average (T3)",
        params=[IndicatorParam("timeperiod", 5, "int"),
                IndicatorParam("vfactor", 0.7, "float")],
        pandas_ta_kind="t3"),
    TalibIndicator("HT_TRENDLINE", "Overlap Studies", "Hilbert Transform - Instantaneous Trendline"),
    TalibIndicator("MIDPOINT", "Overlap Studies", "MidPoint over period",
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="midpoint"),
    TalibIndicator("MIDPRICE", "Overlap Studies", "Midpoint Price over period",
        inputs=("high", "low"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="midprice"),
    TalibIndicator("BBANDS", "Overlap Studies", "Bollinger Bands",
        params=[IndicatorParam("timeperiod", 20, "int"),
                IndicatorParam("nbdevup", 2.0, "float"),
                IndicatorParam("nbdevdn", 2.0, "float")],
        outputs=("upper", "middle", "lower"),
        pandas_ta_kind="bbands", native_class="BBands"),
    TalibIndicator("SAR", "Overlap Studies", "Parabolic SAR",
        inputs=("high", "low"),
        params=[IndicatorParam("acceleration", 0.02, "float"),
                IndicatorParam("maximum", 0.2, "float")],
        pandas_ta_kind="psar", native_class="PSAR"),
    TalibIndicator("SAREXT", "Overlap Studies", "Parabolic SAR (extended)",
        inputs=("high", "low"),
        params=[IndicatorParam("startvalue", 0.0, "float"),
                IndicatorParam("offsetonreverse", 0.0, "float"),
                IndicatorParam("accelerationinitlong", 0.02, "float"),
                IndicatorParam("accelerationlong", 0.02, "float"),
                IndicatorParam("accelerationmaxlong", 0.2, "float"),
                IndicatorParam("accelerationinitshort", 0.02, "float"),
                IndicatorParam("accelerationshort", 0.02, "float"),
                IndicatorParam("accelerationmaxshort", 0.2, "float")]),
]


_MOMENTUM: list[TalibIndicator] = [
    TalibIndicator("RSI", "Momentum Indicators", "Relative Strength Index",
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="rsi", native_class="RSI"),
    TalibIndicator("MACD", "Momentum Indicators", "MACD",
        params=[IndicatorParam("fastperiod", 12, "int"),
                IndicatorParam("slowperiod", 26, "int"),
                IndicatorParam("signalperiod", 9, "int")],
        outputs=("macd", "signal", "hist"),
        pandas_ta_kind="macd", native_class="MACD"),
    TalibIndicator("MACDEXT", "Momentum Indicators", "MACD with controllable MA type",
        params=[IndicatorParam("fastperiod", 12, "int"),
                IndicatorParam("slowperiod", 26, "int"),
                IndicatorParam("signalperiod", 9, "int")],
        outputs=("macd", "signal", "hist")),
    TalibIndicator("MACDFIX", "Momentum Indicators", "MACD Fix 12/26",
        params=[IndicatorParam("signalperiod", 9, "int")],
        outputs=("macd", "signal", "hist")),
    TalibIndicator("STOCH", "Momentum Indicators", "Stochastic Oscillator",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("fastk_period", 5, "int"),
                IndicatorParam("slowk_period", 3, "int"),
                IndicatorParam("slowd_period", 3, "int")],
        outputs=("slowk", "slowd"),
        pandas_ta_kind="stoch", native_class="Stochastic"),
    TalibIndicator("STOCHF", "Momentum Indicators", "Stochastic Fast",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("fastk_period", 5, "int"),
                IndicatorParam("fastd_period", 3, "int")],
        outputs=("fastk", "fastd")),
    TalibIndicator("STOCHRSI", "Momentum Indicators", "Stochastic RSI",
        params=[IndicatorParam("timeperiod", 14, "int"),
                IndicatorParam("fastk_period", 5, "int"),
                IndicatorParam("fastd_period", 3, "int")],
        outputs=("fastk", "fastd"),
        pandas_ta_kind="stochrsi"),
    TalibIndicator("CCI", "Momentum Indicators", "Commodity Channel Index",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="cci", native_class="CCI"),
    TalibIndicator("WILLR", "Momentum Indicators", "Williams' %R",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="willr", native_class="WilliamsR"),
    TalibIndicator("MFI", "Momentum Indicators", "Money Flow Index",
        inputs=("high", "low", "close", "volume"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="mfi", native_class="MFI"),
    TalibIndicator("ULTOSC", "Momentum Indicators", "Ultimate Oscillator",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod1", 7, "int"),
                IndicatorParam("timeperiod2", 14, "int"),
                IndicatorParam("timeperiod3", 28, "int")],
        pandas_ta_kind="uo", native_class="UO"),
    TalibIndicator("AROON", "Momentum Indicators", "Aroon",
        inputs=("high", "low"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        outputs=("aroondown", "aroonup"),
        pandas_ta_kind="aroon", native_class="Aroon"),
    TalibIndicator("AROONOSC", "Momentum Indicators", "Aroon Oscillator",
        inputs=("high", "low"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="aroon"),
    TalibIndicator("ADX", "Momentum Indicators", "Average Directional Movement Index",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="adx", native_class="ADX"),
    TalibIndicator("ADXR", "Momentum Indicators", "Average Directional Movement Rating",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("APO", "Momentum Indicators", "Absolute Price Oscillator",
        params=[IndicatorParam("fastperiod", 12, "int"),
                IndicatorParam("slowperiod", 26, "int")],
        pandas_ta_kind="apo"),
    TalibIndicator("PPO", "Momentum Indicators", "Percentage Price Oscillator",
        params=[IndicatorParam("fastperiod", 12, "int"),
                IndicatorParam("slowperiod", 26, "int")],
        pandas_ta_kind="ppo"),
    TalibIndicator("MOM", "Momentum Indicators", "Momentum",
        params=[IndicatorParam("timeperiod", 10, "int")],
        pandas_ta_kind="mom"),
    TalibIndicator("ROC", "Momentum Indicators", "Rate of Change",
        params=[IndicatorParam("timeperiod", 10, "int")],
        pandas_ta_kind="roc", native_class="ROC"),
    TalibIndicator("ROCP", "Momentum Indicators", "Rate of Change Percentage",
        params=[IndicatorParam("timeperiod", 10, "int")]),
    TalibIndicator("ROCR", "Momentum Indicators", "Rate of Change Ratio",
        params=[IndicatorParam("timeperiod", 10, "int")]),
    TalibIndicator("ROCR100", "Momentum Indicators", "Rate of Change Ratio (×100)",
        params=[IndicatorParam("timeperiod", 10, "int")]),
    TalibIndicator("TRIX", "Momentum Indicators", "1-day ROC of Triple Smooth EMA",
        params=[IndicatorParam("timeperiod", 30, "int")],
        pandas_ta_kind="trix", native_class="TRIX"),
    TalibIndicator("BOP", "Momentum Indicators", "Balance of Power",
        inputs=("open", "high", "low", "close"),
        pandas_ta_kind="bop"),
    TalibIndicator("CMO", "Momentum Indicators", "Chande Momentum Oscillator",
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="cmo"),
    TalibIndicator("DX", "Momentum Indicators", "Directional Movement Index",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("MINUS_DI", "Momentum Indicators", "Minus Directional Indicator",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("PLUS_DI", "Momentum Indicators", "Plus Directional Indicator",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("MINUS_DM", "Momentum Indicators", "Minus Directional Movement",
        inputs=("high", "low"),
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("PLUS_DM", "Momentum Indicators", "Plus Directional Movement",
        inputs=("high", "low"),
        params=[IndicatorParam("timeperiod", 14, "int")]),
]


_VOLUME: list[TalibIndicator] = [
    TalibIndicator("OBV", "Volume Indicators", "On Balance Volume",
        inputs=("close", "volume"),
        pandas_ta_kind="obv", native_class="OBV"),
    TalibIndicator("AD", "Volume Indicators", "Chaikin A/D Line",
        inputs=("high", "low", "close", "volume"),
        pandas_ta_kind="ad"),
    TalibIndicator("ADOSC", "Volume Indicators", "Chaikin A/D Oscillator",
        inputs=("high", "low", "close", "volume"),
        params=[IndicatorParam("fastperiod", 3, "int"),
                IndicatorParam("slowperiod", 10, "int")],
        pandas_ta_kind="adosc", native_class="ChaikinOsc"),
]


_VOLATILITY: list[TalibIndicator] = [
    TalibIndicator("ATR", "Volatility Indicators", "Average True Range",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="atr", native_class="ATR"),
    TalibIndicator("NATR", "Volatility Indicators", "Normalized ATR",
        inputs=("high", "low", "close"),
        params=[IndicatorParam("timeperiod", 14, "int")],
        pandas_ta_kind="natr"),
    TalibIndicator("TRANGE", "Volatility Indicators", "True Range",
        inputs=("high", "low", "close"),
        pandas_ta_kind="true_range"),
]


_PRICE_TRANSFORM: list[TalibIndicator] = [
    TalibIndicator("AVGPRICE", "Price Transform", "Average Price (O+H+L+C)/4",
        inputs=("open", "high", "low", "close")),
    TalibIndicator("MEDPRICE", "Price Transform", "Median Price (H+L)/2",
        inputs=("high", "low")),
    TalibIndicator("TYPPRICE", "Price Transform", "Typical Price (H+L+C)/3",
        inputs=("high", "low", "close")),
    TalibIndicator("WCLPRICE", "Price Transform", "Weighted Close Price (H+L+2C)/4",
        inputs=("high", "low", "close")),
]


_CYCLE: list[TalibIndicator] = [
    TalibIndicator("HT_DCPERIOD", "Cycle Indicators", "Hilbert Transform - Dominant Cycle Period"),
    TalibIndicator("HT_DCPHASE", "Cycle Indicators", "Hilbert Transform - Dominant Cycle Phase"),
    TalibIndicator("HT_PHASOR", "Cycle Indicators", "Hilbert Transform - Phasor Components",
        outputs=("inphase", "quadrature")),
    TalibIndicator("HT_SINE", "Cycle Indicators", "Hilbert Transform - SineWave",
        outputs=("sine", "leadsine")),
    TalibIndicator("HT_TRENDMODE", "Cycle Indicators", "Hilbert Transform - Trend vs Cycle Mode"),
]


_PATTERNS: list[TalibIndicator] = [
    TalibIndicator(p, "Pattern Recognition", desc,
                   inputs=("open", "high", "low", "close"),
                   outputs=("pattern",))
    for p, desc in [
        ("CDL2CROWS", "Two Crows"),
        ("CDL3BLACKCROWS", "Three Black Crows"),
        ("CDL3INSIDE", "Three Inside Up/Down"),
        ("CDL3LINESTRIKE", "Three-Line Strike"),
        ("CDL3OUTSIDE", "Three Outside Up/Down"),
        ("CDL3STARSINSOUTH", "Three Stars In The South"),
        ("CDL3WHITESOLDIERS", "Three Advancing White Soldiers"),
        ("CDLABANDONEDBABY", "Abandoned Baby"),
        ("CDLADVANCEBLOCK", "Advance Block"),
        ("CDLBELTHOLD", "Belt-hold"),
        ("CDLBREAKAWAY", "Breakaway"),
        ("CDLCLOSINGMARUBOZU", "Closing Marubozu"),
        ("CDLCONCEALBABYSWALL", "Concealing Baby Swallow"),
        ("CDLCOUNTERATTACK", "Counterattack"),
        ("CDLDARKCLOUDCOVER", "Dark Cloud Cover"),
        ("CDLDOJI", "Doji"),
        ("CDLDOJISTAR", "Doji Star"),
        ("CDLDRAGONFLYDOJI", "Dragonfly Doji"),
        ("CDLENGULFING", "Engulfing Pattern"),
        ("CDLEVENINGDOJISTAR", "Evening Doji Star"),
        ("CDLEVENINGSTAR", "Evening Star"),
        ("CDLGAPSIDESIDEWHITE", "Up/Down-gap side-by-side white lines"),
        ("CDLGRAVESTONEDOJI", "Gravestone Doji"),
        ("CDLHAMMER", "Hammer"),
        ("CDLHANGINGMAN", "Hanging Man"),
        ("CDLHARAMI", "Harami Pattern"),
        ("CDLHARAMICROSS", "Harami Cross Pattern"),
        ("CDLHIGHWAVE", "High-Wave Candle"),
        ("CDLHIKKAKE", "Hikkake Pattern"),
        ("CDLHIKKAKEMOD", "Modified Hikkake Pattern"),
        ("CDLHOMINGPIGEON", "Homing Pigeon"),
        ("CDLIDENTICAL3CROWS", "Identical Three Crows"),
        ("CDLINNECK", "In-Neck Pattern"),
        ("CDLINVERTEDHAMMER", "Inverted Hammer"),
        ("CDLKICKING", "Kicking"),
        ("CDLKICKINGBYLENGTH", "Kicking by length"),
        ("CDLLADDERBOTTOM", "Ladder Bottom"),
        ("CDLLONGLEGGEDDOJI", "Long Legged Doji"),
        ("CDLLONGLINE", "Long Line Candle"),
        ("CDLMARUBOZU", "Marubozu"),
        ("CDLMATCHINGLOW", "Matching Low"),
        ("CDLMATHOLD", "Mat Hold"),
        ("CDLMORNINGDOJISTAR", "Morning Doji Star"),
        ("CDLMORNINGSTAR", "Morning Star"),
        ("CDLONNECK", "On-Neck Pattern"),
        ("CDLPIERCING", "Piercing Pattern"),
        ("CDLRICKSHAWMAN", "Rickshaw Man"),
        ("CDLRISEFALL3METHODS", "Rising/Falling Three Methods"),
        ("CDLSEPARATINGLINES", "Separating Lines"),
        ("CDLSHOOTINGSTAR", "Shooting Star"),
        ("CDLSHORTLINE", "Short Line Candle"),
        ("CDLSPINNINGTOP", "Spinning Top"),
        ("CDLSTALLEDPATTERN", "Stalled Pattern"),
        ("CDLSTICKSANDWICH", "Stick Sandwich"),
        ("CDLTAKURI", "Takuri (Dragonfly Doji with very long lower shadow)"),
        ("CDLTASUKIGAP", "Tasuki Gap"),
        ("CDLTHRUSTING", "Thrusting Pattern"),
        ("CDLTRISTAR", "Tristar Pattern"),
        ("CDLUNIQUE3RIVER", "Unique 3 River"),
        ("CDLUPSIDEGAP2CROWS", "Upside Gap Two Crows"),
        ("CDLXSIDEGAP3METHODS", "Upside/Downside Gap Three Methods"),
    ]
]


_STATISTIC: list[TalibIndicator] = [
    TalibIndicator("BETA", "Statistic Functions", "Beta",
        inputs=("high", "low"),
        params=[IndicatorParam("timeperiod", 5, "int")]),
    TalibIndicator("CORREL", "Statistic Functions", "Pearson's Correlation Coefficient",
        inputs=("high", "low"),
        params=[IndicatorParam("timeperiod", 30, "int")]),
    TalibIndicator("LINEARREG", "Statistic Functions", "Linear Regression",
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("LINEARREG_ANGLE", "Statistic Functions", "Linear Regression Angle",
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("LINEARREG_INTERCEPT", "Statistic Functions", "Linear Regression Intercept",
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("LINEARREG_SLOPE", "Statistic Functions", "Linear Regression Slope",
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("STDDEV", "Statistic Functions", "Standard Deviation",
        params=[IndicatorParam("timeperiod", 5, "int"),
                IndicatorParam("nbdev", 1.0, "float")],
        native_class="StdDev"),
    TalibIndicator("TSF", "Statistic Functions", "Time Series Forecast",
        params=[IndicatorParam("timeperiod", 14, "int")]),
    TalibIndicator("VAR", "Statistic Functions", "Variance",
        params=[IndicatorParam("timeperiod", 5, "int"),
                IndicatorParam("nbdev", 1.0, "float")]),
]


_MATH_TRANSFORM: list[TalibIndicator] = [
    TalibIndicator(name, "Math Transform", desc)
    for name, desc in [
        ("ACOS", "Vector Trigonometric ACOS"),
        ("ASIN", "Vector Trigonometric ASIN"),
        ("ATAN", "Vector Trigonometric ATAN"),
        ("CEIL", "Vector Ceil"),
        ("COS", "Vector Trigonometric COS"),
        ("COSH", "Vector Trigonometric COSH"),
        ("EXP", "Vector Arithmetic EXP"),
        ("FLOOR", "Vector Floor"),
        ("LN", "Vector Log Natural"),
        ("LOG10", "Vector Log10"),
        ("SIN", "Vector Trigonometric SIN"),
        ("SINH", "Vector Trigonometric SINH"),
        ("SQRT", "Vector Square Root"),
        ("TAN", "Vector Trigonometric TAN"),
        ("TANH", "Vector Trigonometric TANH"),
    ]
]


_MATH_OPERATOR: list[TalibIndicator] = [
    TalibIndicator("ADD", "Math Operators", "Vector Arithmetic Add",
        inputs=("high", "low")),
    TalibIndicator("SUB", "Math Operators", "Vector Arithmetic Subtract",
        inputs=("high", "low")),
    TalibIndicator("MULT", "Math Operators", "Vector Arithmetic Multiply",
        inputs=("high", "low")),
    TalibIndicator("DIV", "Math Operators", "Vector Arithmetic Divide",
        inputs=("high", "low")),
    TalibIndicator("MAX", "Math Operators", "Highest value over a period",
        params=[IndicatorParam("timeperiod", 30, "int")]),
    TalibIndicator("MIN", "Math Operators", "Lowest value over a period",
        params=[IndicatorParam("timeperiod", 30, "int")]),
    TalibIndicator("MAXINDEX", "Math Operators", "Index of highest value over a period",
        params=[IndicatorParam("timeperiod", 30, "int")]),
    TalibIndicator("MININDEX", "Math Operators", "Index of lowest value over a period",
        params=[IndicatorParam("timeperiod", 30, "int")]),
    TalibIndicator("MINMAX", "Math Operators", "Lowest/highest value over a period",
        outputs=("min", "max"),
        params=[IndicatorParam("timeperiod", 30, "int")]),
    TalibIndicator("SUM", "Math Operators", "Summation",
        params=[IndicatorParam("timeperiod", 30, "int")]),
]


ALL_TALIB: list[TalibIndicator] = (
    _OVERLAP
    + _MOMENTUM
    + _VOLUME
    + _VOLATILITY
    + _PRICE_TRANSFORM
    + _CYCLE
    + _PATTERNS
    + _STATISTIC
    + _MATH_TRANSFORM
    + _MATH_OPERATOR
)


_BY_NAME: dict[str, TalibIndicator] = {ind.name: ind for ind in ALL_TALIB}


def find(name: str) -> TalibIndicator | None:
    return _BY_NAME.get(name.upper())


def can_compute(ind: TalibIndicator) -> bool:
    if _TALIB is not None and hasattr(_TALIB, ind.name):
        return True
    if _PANDAS_TA is not None and ind.pandas_ta_kind:
        return True
    if ind.native_class:
        return True
    return False


def catalog() -> dict[str, Any]:
    """Return the full catalog grouped by TA-Lib group."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for ind in ALL_TALIB:
        groups.setdefault(ind.group, []).append({
            "id": ind.name,
            "name": ind.name,
            "group": ind.group,
            "description": ind.description,
            "inputs": list(ind.inputs),
            "outputs": list(ind.outputs),
            "params": [
                {
                    "name": p.name,
                    "default": p.default,
                    "type": p.type,
                    "description": p.description,
                }
                for p in ind.params
            ],
            "engine": _engine_for(ind),
            "can_compute": can_compute(ind),
        })
    return {
        "engines": engine_status(),
        "groups": [
            {"name": g, "indicators": inds}
            for g, inds in sorted(groups.items())
        ],
        "total": sum(len(g) for g in groups.values()),
    }


def _engine_for(ind: TalibIndicator) -> str:
    if _TALIB is not None and hasattr(_TALIB, ind.name):
        return "talib"
    if _PANDAS_TA is not None and ind.pandas_ta_kind:
        return "pandas_ta"
    if ind.native_class:
        return "native"
    return "none"


# ---------------------------------------------------------------------------
# Compute helpers — used by IndicatorZoo as a fallback.
# ---------------------------------------------------------------------------


def compute_via_talib(
    ind: TalibIndicator,
    bars: pd.DataFrame,
    kwargs: dict[str, Any],
) -> dict[str, list[float]] | None:
    """Compute one TA-Lib function for a single symbol's bars frame.

    Returns ``{output_name: [...]}`` or ``None`` if talib cannot run it.
    """
    if _TALIB is None or not hasattr(_TALIB, ind.name):
        return None
    fn = getattr(_TALIB, ind.name)
    try:
        args = [bars[col].astype(float).to_numpy() for col in ind.inputs]
    except KeyError:
        return None
    safe_kwargs = {
        k: v
        for k, v in kwargs.items()
        if k in {p.name for p in ind.params}
    }
    try:
        result = fn(*args, **safe_kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("talib %s failed", ind.name)
        return None

    if isinstance(result, tuple):
        return {
            ind.outputs[i] if i < len(ind.outputs) else f"out_{i}": list(map(float, arr))
            for i, arr in enumerate(result)
        }
    return {ind.outputs[0] if ind.outputs else "value": list(map(float, result))}


def compute_via_pandas_ta(
    ind: TalibIndicator,
    bars: pd.DataFrame,
    kwargs: dict[str, Any],
) -> dict[str, list[float]] | None:
    """Compute via ``pandas_ta`` when ``pandas_ta_kind`` is set."""
    if _PANDAS_TA is None or not ind.pandas_ta_kind:
        return None
    df = bars.copy()
    df.columns = [c.lower() for c in df.columns]
    try:
        accessor = df.ta  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None
    fn = getattr(accessor, ind.pandas_ta_kind, None)
    if fn is None:
        return None
    try:
        result = fn(**kwargs)
    except Exception:  # noqa: BLE001
        try:
            result = fn()
        except Exception:  # noqa: BLE001
            logger.exception("pandas_ta %s failed", ind.pandas_ta_kind)
            return None

    if isinstance(result, pd.DataFrame):
        return {col: result[col].astype(float).tolist() for col in result.columns}
    if isinstance(result, pd.Series):
        return {ind.outputs[0] if ind.outputs else "value": result.astype(float).tolist()}
    return None


__all__ = [
    "TalibIndicator",
    "IndicatorParam",
    "ALL_TALIB",
    "find",
    "catalog",
    "can_compute",
    "compute_via_talib",
    "compute_via_pandas_ta",
    "engine_status",
]
