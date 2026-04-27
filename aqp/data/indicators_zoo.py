"""Batch application of :mod:`aqp.core.indicators` to tidy bars frames.

The core indicators are *online* state machines designed for streaming
data. This module wraps them into ergonomic DataFrame transformers so
you can produce a feature panel from a long-format bars table in a
single call.

Usage::

    zoo = IndicatorZoo()
    feats = zoo.transform(bars, indicators=["SMA:20", "RSI:14", "MACD"])
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

from aqp.core.indicators import (
    ALL_INDICATORS,
    BollingerBands,
    IndicatorBase,
    KeltnerChannels,
    MovingAverageConvergenceDivergence,
    Stochastic,
)
from aqp.data import talib_catalog
from aqp.data.model_prediction import apply_model_predictions, is_model_pred_spec

logger = logging.getLogger(__name__)


# Indicators whose ``current`` is their primary value — we add extra
# multi-value columns for these.
_EXTRA_OUTPUTS: dict[type, list[str]] = {
    BollingerBands: ["upper", "middle", "lower"],
    KeltnerChannels: ["upper", "middle", "lower"],
    MovingAverageConvergenceDivergence: ["signal_value", "histogram"],
    Stochastic: ["k_value", "d_value"],
}


@dataclass
class IndicatorSpec:
    """A single indicator request: class name + constructor kwargs."""

    name: str
    kwargs: dict

    @classmethod
    def parse(cls, spec: str) -> IndicatorSpec:
        """Parse ``"SMA:20"`` → ``IndicatorSpec("SMA", {"period": 20})``."""
        if ":" not in spec:
            return cls(name=spec, kwargs={})
        name, tail = spec.split(":", 1)
        # Comma-separated k=v or bare period first
        parts = tail.split(",")
        kwargs: dict = {}
        for i, p in enumerate(parts):
            if "=" in p:
                k, v = p.split("=", 1)
                kwargs[k.strip()] = _coerce(v.strip())
            elif i == 0 and p.strip().isdigit():
                kwargs["period"] = int(p.strip())
            else:
                kwargs[f"arg_{i}"] = _coerce(p.strip())
        return cls(name=name, kwargs=kwargs)


def _coerce(val: str):
    try:
        return int(val)
    except ValueError:
        try:
            return float(val)
        except ValueError:
            return val


class IndicatorZoo:
    """Apply one or more indicators to a tidy bars frame."""

    def __init__(self, extra_classes: dict[str, type[IndicatorBase]] | None = None) -> None:
        self._extra_classes = extra_classes or {}

    def known(self) -> list[str]:
        names: set[str] = {*ALL_INDICATORS.keys(), *self._extra_classes.keys()}
        for ind in talib_catalog.ALL_TALIB:
            if talib_catalog.can_compute(ind):
                names.add(ind.name)
        return sorted(names)

    def transform(
        self,
        bars: pd.DataFrame,
        indicators: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        """Add one column per indicator to ``bars`` (preserves input rows).

        ``ModelPred:...`` specs are applied as a vectorised post-step so
        deployed-model predictions can land in the feature panel
        alongside classical TA indicators.
        """
        if bars.empty:
            return bars
        all_specs = [IndicatorSpec.parse(s) for s in (indicators or _default_specs())]
        ta_specs: list[IndicatorSpec] = []
        model_specs: list[tuple[str, dict]] = []
        for spec in all_specs:
            if is_model_pred_spec(spec.name):
                model_specs.append((spec.name, dict(spec.kwargs)))
            else:
                ta_specs.append(spec)
        specs = ta_specs
        frames: list[pd.DataFrame] = []
        for _vt_symbol, sub in bars.sort_values("timestamp").groupby("vt_symbol", sort=False):
            sub = sub.copy()
            for spec in specs:
                cls = self._extra_classes.get(spec.name) or ALL_INDICATORS.get(spec.name)
                if cls is None:
                    talib_result = _compute_talib_spec(spec, sub)
                    if talib_result is not None:
                        col_name = _col_name(spec)
                        primary_key = next(iter(talib_result))
                        sub[col_name] = talib_result[primary_key]
                        for k, vals in talib_result.items():
                            if k == primary_key:
                                continue
                            sub[f"{col_name}_{k}"] = vals
                        continue
                    logger.warning("unknown indicator: %s", spec.name)
                    continue
                try:
                    ind = cls(**spec.kwargs)
                except TypeError:
                    # Fall back to zero-arg construction.
                    try:
                        ind = cls()
                    except Exception:
                        logger.exception("could not construct %s", spec.name)
                        continue
                values: list[float] = []
                extra_cols: dict[str, list[float]] = {
                    name: [] for name in _EXTRA_OUTPUTS.get(type(ind), [])
                }
                for _, row in sub.iterrows():
                    payload = _row_to_indicator_input(ind, row)
                    try:
                        val = ind.update(payload, row["timestamp"])
                    except Exception:
                        val = float("nan")
                    values.append(val)
                    for name in extra_cols:
                        extra_cols[name].append(getattr(ind, name, float("nan")))
                col_name = _col_name(spec)
                sub[col_name] = values
                for extra_name, extra_vals in extra_cols.items():
                    sub[f"{col_name}_{extra_name}"] = extra_vals
            frames.append(sub)
        out = pd.concat(frames, ignore_index=True)
        if model_specs:
            try:
                out = apply_model_predictions(out, model_specs)
            except Exception:
                logger.exception("ModelPrediction post-step failed")
        return out


def _default_specs() -> list[str]:
    return [
        "SMA:20",
        "SMA:50",
        "EMA:12",
        "EMA:26",
        "RSI:14",
        "MACD",
        "BBands:20",
        "ATR:14",
        "Z:20",
        "LogReturn:1",
    ]


def from_pandas_ta(
    bars: pd.DataFrame,
    strategy: str | list[str] = "common",
) -> pd.DataFrame:
    """Optional bridge into ``pandas-ta``.

    Install via ``pip install -e ".[ml]"`` (``pandas-ta-classic`` ships in the
    ``ml`` extra). Pass a list of pandas-ta kind strings (e.g. ``["rsi", "adx"]``) or
    the string ``"common"`` (which applies a reasonable built-in set).

    Returns the input ``bars`` with extra columns appended (inplace semantics
    are preserved for pandas_ta compatibility).
    """
    try:
        import pandas_ta as pta  # type: ignore[import]
    except ImportError:
        try:
            import pandas_ta_classic as pta  # type: ignore[import]
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "pandas-ta-classic is not installed. Install with `pip install -e \".[ml]\"`"
            ) from e

    if bars.empty:
        return bars
    frames = []
    for _vt, sub in bars.sort_values("timestamp").groupby("vt_symbol", sort=False):
        sub = sub.copy()
        sub.index = pd.to_datetime(sub["timestamp"])
        # Rename to pandas-ta's OHLCV conventions.
        renamed = sub.rename(
            columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
        )
        try:
            if strategy == "common":
                renamed.ta.strategy(pta.CommonStrategy)
            elif isinstance(strategy, list):
                for kind in strategy:
                    getattr(renamed.ta, kind)(append=True)
            else:
                renamed.ta.strategy(strategy)
        except Exception:
            logger.exception("pandas_ta failed on %s", sub["vt_symbol"].iloc[0] if len(sub) else "?")
        renamed = renamed.reset_index(drop=True)
        # Keep lower-case OHLCV for our downstream tooling.
        renamed = renamed.rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )
        frames.append(renamed)
    return pd.concat(frames, ignore_index=True) if frames else bars


def _col_name(spec: IndicatorSpec) -> str:
    if "period" in spec.kwargs:
        return f"{spec.name.lower()}_{spec.kwargs['period']}"
    if spec.kwargs:
        tail = "_".join(f"{k}{v}" for k, v in spec.kwargs.items())
        return f"{spec.name.lower()}_{tail}"
    return spec.name.lower()


def _row_to_indicator_input(indicator: IndicatorBase, row: pd.Series):
    """Some indicators accept ``BarData``-like input; others accept ``float``.

    We build a lightweight object here so we don't construct a full
    ``BarData`` per row.
    """
    from aqp.core.types import BarData, Symbol

    # Probe: if ``_extract_value`` expects a BarData, pass one.
    probe_sig = indicator._extract_value  # noqa: SLF001
    try:
        sym = Symbol.parse(row["vt_symbol"])
        bar = BarData(
            symbol=sym,
            timestamp=row["timestamp"],
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        probe_sig(bar)
        return bar
    except Exception:
        return float(row["close"])


# ---------------------------------------------------------------------------
# Keep the old FeatureEngineer API but delegate to the zoo
# ---------------------------------------------------------------------------


DEFAULT_FEATURE_SPECS = _default_specs()


# ---------------------------------------------------------------------------
# TA-Lib / pandas-ta dispatch
# ---------------------------------------------------------------------------


def _compute_talib_spec(spec: IndicatorSpec, sub: pd.DataFrame) -> dict[str, list[float]] | None:
    """Try to compute a TA-Lib catalog indicator on a single-symbol bars frame.

    Returns ``{output_name: list_of_values}`` (preserving row order) or
    ``None`` when no engine is available.
    """
    ind = talib_catalog.find(spec.name)
    if ind is None:
        return None
    talib_result = talib_catalog.compute_via_talib(ind, sub, dict(spec.kwargs))
    if talib_result is not None:
        return talib_result
    pta_result = talib_catalog.compute_via_pandas_ta(ind, sub, dict(spec.kwargs))
    if pta_result is not None:
        return pta_result
    return None
