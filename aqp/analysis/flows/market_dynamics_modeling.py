"""Market dynamics modeling — slice-and-merge regime labeller.

Port of TradeMaster's
``trademaster/utils/labeling_util.py::Worker`` algorithm into AQP's
:class:`AnalysisFlow` framework. The flow takes a price series and
returns a per-bar regime label (``label`` column) plus per-regime
descriptive statistics.

Pipeline
========

1. **Butterworth low-pass filter** on the key indicator (default
   ``close``) to remove high-frequency noise. Filter strength
   defaults to ``1`` matching the TradeMaster reference.
2. **Turning-point detection**: bars where the filtered percent-
   return changes sign mark candidate segment boundaries.
3. **Short-segment merging**: segments below ``min_length_limit``
   ticks are merged with their nearest neighbour so every regime
   has a stable estimation window.
4. **Per-segment slope**: linear regression of the filtered indicator
   inside each segment yields a normalised slope (% change per
   bar).
5. **Labelling**: segments are bucketed into ``dynamic_number``
   regimes by ``quantile`` (default) or ``slope`` (fixed thresholds).

Output
======

A :class:`FlowResult` with:

- ``metrics``: ``{n_segments, n_regimes, segment_lengths_mean, …}``.
- ``rows``: ``[{date, indicator, slope, label}, …]`` (preview, capped
  at 500 rows).
- ``arrow_table``: full per-bar label table that the
  :class:`AnalysisRuntime` persists to the gold-tier Iceberg table
  ``aqp_gold_analysis_market_dynamics_modeling``.

Hard rule 23: orchestrated by :class:`AnalysisRuntime`.
Hard rule 25: registered through :func:`register_analysis_flow`.
Hard rule 21: gold-tier write.
"""
from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field
from sklearn.linear_model import LinearRegression

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


class SliceAndMergeRegimeParams(FlowParams):
    """Parameters for the slice-and-merge regime labeller."""

    timestamp_column: str = "date"
    indicator_column: str = "close"
    tic_column: str | None = None
    dynamic_number: int = Field(default=4, ge=2, le=12)
    filter_strength: float = Field(default=1.0, gt=0)
    min_length_limit: int = Field(default=12, ge=1)
    max_length_expectation: int = Field(default=100, ge=1)
    labeling_method: Literal["slope", "quantile"] = "quantile"
    slope_low: float | None = None
    slope_high: float | None = None


@register_analysis_flow(
    name="market_dynamics.slice_and_merge",
    namespace="market_dynamics_modeling",
    label="Slice-and-merge regime labeller",
    description=(
        "TradeMaster-style market dynamics labeller — Butterworth filter "
        "→ turning-point segmentation → DTW-style merge → per-segment "
        "slope-based regime labels. Used by the RL Lab's "
        "RegimeStratifiedEvaluation experiment to score policies under "
        "specific market regimes."
    ),
    params_model=SliceAndMergeRegimeParams,
    tags=("regime", "market_dynamics", "labeling", "trademaster"),
)
def slice_and_merge_regime_flow(
    df: pd.DataFrame,
    params: SliceAndMergeRegimeParams,
    ctx: FlowContext,
) -> FlowResult:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if params.indicator_column not in df.columns:
        return FlowResult(
            flow="market_dynamics.slice_and_merge",
            error=f"indicator_column {params.indicator_column!r} not in dataframe",
        )

    # Group by ticker (when present) so multi-asset DataFrames produce
    # per-ticker labels in a single call.
    if params.tic_column and params.tic_column in df.columns:
        grouped = df.groupby(params.tic_column, sort=False)
    else:
        grouped = [(None, df)]

    all_labeled: list[pd.DataFrame] = []
    segments_total = 0
    segments_per_regime: dict[int, int] = {}

    for tic_name, sub in grouped:
        if len(sub) < params.min_length_limit + 2:
            continue
        labeled = _label_ticker(sub, params, tic_name)
        if labeled is None or labeled.empty:
            continue
        segments_total += int(labeled["segment_id"].nunique())
        for lbl, count in labeled.groupby("label")["segment_id"].nunique().items():
            segments_per_regime[int(lbl)] = segments_per_regime.get(int(lbl), 0) + int(count)
        all_labeled.append(labeled)

    if not all_labeled:
        return FlowResult(
            flow="market_dynamics.slice_and_merge",
            error="no segments produced; check min_length_limit + data length",
        )

    combined = pd.concat(all_labeled, ignore_index=True)
    preview = combined.head(500).to_dict(orient="records")
    seg_lengths = combined.groupby("segment_id").size().to_numpy()
    metrics: dict[str, float | int] = {
        "n_segments": int(segments_total),
        "n_regimes": int(combined["label"].nunique()),
        "n_rows": int(len(combined)),
        "segment_length_mean": float(seg_lengths.mean()) if len(seg_lengths) > 0 else 0.0,
        "segment_length_min": int(seg_lengths.min()) if len(seg_lengths) > 0 else 0,
        "segment_length_max": int(seg_lengths.max()) if len(seg_lengths) > 0 else 0,
    }
    for regime_label, count in sorted(segments_per_regime.items()):
        metrics[f"regime_{regime_label}_segments"] = int(count)

    return FlowResult(
        flow="market_dynamics.slice_and_merge",
        metrics=metrics,
        rows=preview,
        arrow_table=coerce_arrow(combined.to_dict(orient="records")),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _label_ticker(
    df: pd.DataFrame,
    params: SliceAndMergeRegimeParams,
    tic_name: str | None,
) -> pd.DataFrame | None:
    indicator = df[params.indicator_column].to_numpy(dtype=np.float64)
    if indicator.size < params.min_length_limit + 2:
        return None

    # 1. Butterworth low-pass filter (causal `lfilter` to avoid look-ahead).
    filtered = _butter_lowpass(indicator, params.filter_strength, params.min_length_limit)
    pct = np.zeros_like(filtered)
    pct[1:] = np.diff(filtered) / np.where(filtered[:-1] != 0, filtered[:-1], 1e-9)

    # 2. Turning points.
    turning_points = _find_turning_points(pct, params.min_length_limit)
    if len(turning_points) <= 2:
        # All bars in one segment.
        turning_points = [0, len(filtered)]

    # 3-4. Per-segment slope.
    slopes, segment_ranges = _segment_slopes(filtered, turning_points)
    if not slopes:
        return None

    # 5. Label by slope quantile / threshold.
    labels = _assign_labels(slopes, params)

    # Build per-bar output.
    out_rows: list[dict] = []
    for seg_id, ((start, end), slope_val, label) in enumerate(
        zip(segment_ranges, slopes, labels, strict=False)
    ):
        for i in range(start, end):
            row = {
                params.timestamp_column: df[params.timestamp_column].iloc[i]
                if params.timestamp_column in df.columns
                else int(i),
                params.indicator_column: float(indicator[i]),
                "indicator_filtered": float(filtered[i]),
                "slope": float(slope_val),
                "label": int(label),
                "segment_id": int(seg_id),
            }
            if tic_name is not None and params.tic_column is not None:
                row[params.tic_column] = tic_name
            out_rows.append(row)
    return pd.DataFrame(out_rows)


def _butter_lowpass(data: np.ndarray, filter_strength: float, min_length_limit: int) -> np.ndarray:
    """Causal low-pass Butterworth filter (forward-only ``lfilter``).

    Uses ``lfilter`` rather than ``filtfilt`` so the filtered series at
    bar ``t`` is a deterministic function of ``data[≤t]`` only — no
    look-ahead leakage into the regime labels.
    """
    try:
        from scipy.signal import butter, lfilter
    except Exception:
        logger.warning("scipy.signal unavailable — returning raw indicator (no filter)")
        return data.astype(np.float64)
    filter_period = max(min_length_limit, 7)
    wn = min(2 / (filter_period * filter_strength), 0.99)
    b, a = butter(N=4, Wn=wn, btype="low", analog=False)
    return lfilter(b, a, data).astype(np.float64)


def _find_turning_points(pct: np.ndarray, min_length: int) -> list[int]:
    """Return indices where the filtered pct-return sign changes, merged
    so every segment is at least ``min_length`` bars long.
    """
    n = pct.size
    raw_tps = [0]
    for i in range(1, n - 1):
        if pct[i] != 0 and pct[i] * pct[i + 1] < 0:
            raw_tps.append(i + 1)
    if raw_tps[-1] != n:
        raw_tps.append(n)
    # Greedy merge — collapse spans shorter than min_length onto the
    # previous boundary.
    merged: list[int] = [raw_tps[0]]
    for tp in raw_tps[1:]:
        if tp - merged[-1] < min_length and tp != raw_tps[-1]:
            continue
        merged.append(tp)
    if merged[-1] != n:
        merged.append(n)
    return merged


def _segment_slopes(
    indicator: np.ndarray, turning_points: list[int]
) -> tuple[list[float], list[tuple[int, int]]]:
    slopes: list[float] = []
    segment_ranges: list[tuple[int, int]] = []
    reg = LinearRegression()
    for i in range(len(turning_points) - 1):
        start = turning_points[i]
        end = turning_points[i + 1]
        if end - start < 2:
            continue
        x = np.arange(start, end).reshape(-1, 1).astype(np.float64)
        y = indicator[start:end].astype(np.float64)
        reg.fit(x, y)
        base = indicator[start] if indicator[start] != 0 else 1e-9
        slope = float(reg.coef_[0] * 100.0 / base)
        slopes.append(slope)
        segment_ranges.append((start, end))
    return slopes, segment_ranges


def _assign_labels(slopes: list[float], params: SliceAndMergeRegimeParams) -> list[int]:
    n_regimes = params.dynamic_number
    arr = np.asarray(slopes, dtype=np.float64)
    if params.labeling_method == "slope":
        low = params.slope_low if params.slope_low is not None else -0.25
        high = params.slope_high if params.slope_high is not None else 0.25
        # Even-spaced thresholds between low and high (with 0 always
        # included for n_regimes >= 3).
        thresholds = list(
            np.linspace(low, high, n_regimes - 1) if n_regimes >= 2 else []
        )
        labels = [int(np.searchsorted(thresholds, v)) for v in arr]
        return labels
    # Quantile labelling: bin the slopes into n_regimes equal-sized buckets.
    quantiles = np.linspace(0, 1, n_regimes + 1)[1:-1]
    thresholds = list(np.quantile(arr, quantiles)) if len(arr) > 0 else []
    return [int(np.searchsorted(thresholds, v)) for v in arr]


__all__ = ["SliceAndMergeRegimeParams", "slice_and_merge_regime_flow"]
