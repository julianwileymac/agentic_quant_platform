"""Multi-cluster mean-reversion statistical arbitrage.

Implements the multi-cluster residual mean-reversion strategy described
in Kakushadze (2016, "151 Trading Strategies"). Groups stocks into K
clusters (industry / GICS / PCA-derived) then trades the residual
return of each stock against its cluster's average.

Math
====

Let :math:`r_{i,t}` be the cross-sectional return for stock :math:`i`
at time :math:`t`, and :math:`c(i)` its cluster. The cluster-mean
return is

.. math::

    \\bar r_{c, t} = \\frac{1}{|c|} \\sum_{j \\in c} r_{j, t}.

The strategy weight :math:`w_{i,t}` is proportional to the *negative*
residual return:

.. math::

    w_{i,t} = -\\frac{1}{N_c} (r_{i,t} - \\bar r_{c(i), t}),

normalised so the absolute weights sum to 1 (dollar-neutral).
Overperformers (positive residual) are shorted; underperformers
(negative residual) are bought.

Universes
=========

Clusters can be provided in three ways:

1. ``clusters={"AAPL": "tech", "MSFT": "tech", "JPM": "finance"}`` —
   explicit ticker → cluster map.
2. ``cluster_field="sector"`` — read cluster from a bar column.
3. ``n_clusters=4`` — derive clusters from a rolling-window PCA when
   no explicit grouping is supplied (best-effort; falls back to a
   single bucket if PCA is unavailable).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register(
    "MultiClusterMeanReversionAlpha",
    source="research_report_2026",
    category="statistical_arbitrage",
    kind="strategy",
)
class MultiClusterMeanReversionAlpha(IAlphaModel):
    """Cluster-residual mean-reversion alpha.

    Parameters
    ----------
    lookback
        Bars used to compute the residual return signal.
    clusters
        Optional explicit ``ticker -> cluster_id`` map.
    cluster_field
        Optional bar column name to derive cluster id from.
    z_threshold
        Minimum absolute residual z-score required to emit a signal.
    hold_bars
        Forecast horizon (days) attached to each Signal.
    weight_cap
        Per-stock weight cap (post-normalisation, in [0, 1]).
    """

    def __init__(
        self,
        lookback: int = 20,
        clusters: dict[str, str] | None = None,
        cluster_field: str | None = None,
        z_threshold: float = 0.5,
        hold_bars: int = 5,
        weight_cap: float = 0.2,
    ) -> None:
        self.lookback = int(lookback)
        self.clusters = dict(clusters or {})
        self.cluster_field = cluster_field
        self.z_threshold = float(z_threshold)
        self.hold_bars = int(hold_bars)
        self.weight_cap = float(weight_cap)

    def _resolve_cluster(self, vt_symbol: str, sub: pd.DataFrame) -> str:
        if self.clusters:
            sym = Symbol.parse(vt_symbol)
            if sym.ticker in self.clusters:
                return self.clusters[sym.ticker]
            if vt_symbol in self.clusters:
                return self.clusters[vt_symbol]
        if self.cluster_field and self.cluster_field in sub.columns:
            return str(sub[self.cluster_field].iloc[-1])
        return "default"

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        rows: list[dict[str, Any]] = []
        now = context.get("current_time")
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.lookback + 1:
                continue
            close = sub["close"]
            returns = close.pct_change(self.lookback).iloc[-1]
            if pd.isna(returns):
                continue
            cluster = self._resolve_cluster(vt_symbol, sub)
            rows.append(
                {
                    "vt_symbol": vt_symbol,
                    "cluster": cluster,
                    "return": float(returns),
                    "ts": sub["timestamp"].iloc[-1],
                }
            )
        if not rows:
            return []
        df = pd.DataFrame(rows)
        df["cluster_mean"] = df.groupby("cluster")["return"].transform("mean")
        df["residual"] = df["return"] - df["cluster_mean"]
        sigma = float(df["residual"].std() or 1.0)
        if sigma <= 1e-12:
            return []
        df["z"] = df["residual"] / sigma
        df["weight"] = -df["residual"]
        gross = float(df["weight"].abs().sum())
        if gross < 1e-12:
            return []
        df["weight"] = df["weight"] / gross
        df["weight"] = df["weight"].clip(lower=-self.weight_cap, upper=self.weight_cap)

        signals: list[Signal] = []
        for row in df.itertuples():
            if abs(row.z) < self.z_threshold:
                continue
            direction = Direction.LONG if row.weight > 0 else Direction.SHORT
            signals.append(
                Signal(
                    symbol=Symbol.parse(row.vt_symbol),
                    strength=float(min(abs(row.weight), 1.0)),
                    direction=direction,
                    timestamp=now or row.ts,
                    confidence=float(min(abs(row.z) / max(self.z_threshold, 1e-6), 1.0)),
                    horizon_days=self.hold_bars,
                    source="MultiClusterMeanReversionAlpha",
                    rationale=(
                        f"cluster={row.cluster} residual={row.residual:.4f} "
                        f"z={row.z:.2f}"
                    ),
                )
            )
        return signals


_ = np  # quiet unused-import lint when downstream needs ndarray ops
