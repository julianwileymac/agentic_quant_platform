"""FinRL-Trading-style Random Forest stock selector alpha.

Based on the ``FinRL_Full_selection.ipynb`` pattern: train a random
forest on a panel of fundamentals + technical features to predict a
forward return rank, then, at each rebalance, emit long signals for
the top-``k`` stocks (and optionally short the bottom-``k``).

Design:

- Training data is built on the fly from the Parquet lake + yfinance
  fundamentals (or a user-supplied dataset config). Each row is
  ``(symbol, timestamp) -> features -> label``.
- The label is forward n-day return rank; by default we rank within
  each timestamp and binarize into ``top / middle / bottom`` buckets.
- ``generate_signals`` scores the current universe with the trained
  model and emits long/short :class:`Signal` objects.

Lightweight by design — drop-in for users who want an ML-based selector
without configuring the full qlib pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

logger = logging.getLogger(__name__)


DEFAULT_FEATURES = [
    "return_1",
    "return_5",
    "return_10",
    "return_21",
    "vol_21",
    "rsi_14",
    "close_over_sma_50",
]


def _compute_features(bars: pd.DataFrame) -> pd.DataFrame:
    """Pandas feature panel used by both train + score paths."""
    df = bars.sort_values(["vt_symbol", "timestamp"]).copy()
    df["return_1"] = df.groupby("vt_symbol")["close"].pct_change(1)
    df["return_5"] = df.groupby("vt_symbol")["close"].pct_change(5)
    df["return_10"] = df.groupby("vt_symbol")["close"].pct_change(10)
    df["return_21"] = df.groupby("vt_symbol")["close"].pct_change(21)
    df["vol_21"] = (
        df.groupby("vt_symbol")["return_1"].rolling(21).std().reset_index(level=0, drop=True)
    )
    # RSI-14 using simple pandas version
    delta = df.groupby("vt_symbol")["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.groupby(df["vt_symbol"]).rolling(14).mean().reset_index(level=0, drop=True)
    avg_loss = loss.groupby(df["vt_symbol"]).rolling(14).mean().reset_index(level=0, drop=True)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi_14"] = 100 - 100 / (1 + rs)
    sma50 = (
        df.groupby("vt_symbol")["close"].rolling(50).mean().reset_index(level=0, drop=True)
    )
    df["close_over_sma_50"] = df["close"] / sma50
    return df


@register("MLSelectorAlpha")
class MLSelectorAlpha(IAlphaModel):
    """Random-forest based top-k stock selector.

    Parameters
    ----------
    top_k / bottom_k:
        How many symbols to long / short each rebalance.
    forward_days:
        Label horizon used during training (forward-return window).
    features:
        Column names to use. Defaults to :data:`DEFAULT_FEATURES`.
    model_path:
        Optional path to a pre-fit sklearn estimator (joblib). When not
        supplied the alpha fits on the first ``generate_signals`` call
        using the provided historical bars.
    min_history_days:
        Minimum history required before training / scoring.
    long_short:
        If True, emit short signals for the bottom-``bottom_k`` symbols.
    """

    def __init__(
        self,
        top_k: int = 5,
        bottom_k: int = 0,
        forward_days: int = 5,
        features: list[str] | None = None,
        model_path: str | None = None,
        min_history_days: int = 60,
        long_short: bool = False,
        strength: float = 0.2,
    ) -> None:
        self.top_k = int(top_k)
        self.bottom_k = int(bottom_k)
        self.forward_days = int(forward_days)
        self.features = list(features or DEFAULT_FEATURES)
        self.model_path = Path(model_path) if model_path else None
        self.min_history_days = int(min_history_days)
        self.long_short = bool(long_short) or self.bottom_k > 0
        self.strength = float(strength)
        self._model: Any | None = None

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def _maybe_load(self) -> None:
        if self._model is not None or not self.model_path:
            return
        try:
            import joblib

            self._model = joblib.load(self.model_path)
        except Exception as exc:  # pragma: no cover - optional
            logger.warning("failed to load model at %s: %s", self.model_path, exc)
            self._model = None

    def _fit(self, bars: pd.DataFrame) -> None:
        from sklearn.ensemble import RandomForestClassifier

        df = _compute_features(bars)
        df["forward_return"] = (
            df.groupby("vt_symbol")["close"].pct_change(self.forward_days).shift(-self.forward_days)
        )
        df = df.dropna(subset=self.features + ["forward_return"])
        if df.empty:
            logger.info("insufficient data to fit MLSelectorAlpha; emitting no signals")
            self._model = None
            return
        ranks = df.groupby("timestamp")["forward_return"].rank(pct=True)
        df["label"] = pd.cut(
            ranks,
            bins=[-0.01, 0.33, 0.66, 1.01],
            labels=[0, 1, 2],
        ).astype(int)
        X = df[self.features].values
        y = df["label"].values
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=6,
            random_state=42,
            class_weight="balanced",
        )
        model.fit(X, y)
        self._model = model

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty or not universe:
            return []

        self._maybe_load()
        if self._model is None:
            self._fit(bars)
        if self._model is None:
            return []

        feats = _compute_features(bars)
        last = (
            feats.sort_values("timestamp")
            .groupby("vt_symbol")
            .tail(1)
            .dropna(subset=self.features)
        )
        if last.empty:
            return []

        universe_vt = {s.vt_symbol for s in universe}
        last = last[last["vt_symbol"].isin(universe_vt)]
        if last.empty:
            return []

        X = last[self.features].values
        try:
            proba = self._model.predict_proba(X)
            # Probability of label "2" (top bucket) minus label "0" (bottom bucket).
            score = proba[:, -1] - proba[:, 0]
        except Exception:  # pragma: no cover
            score = self._model.predict(X).astype(float)

        last = last.assign(_score=score).sort_values("_score", ascending=False)
        ts = context.get("current_time") or datetime.utcnow()

        tops = last.head(self.top_k)
        bottoms = last.tail(self.bottom_k) if self.long_short and self.bottom_k else last.iloc[0:0]

        sym_by_vt = {s.vt_symbol: s for s in universe}
        signals: list[Signal] = []
        for _, row in tops.iterrows():
            sym = sym_by_vt.get(row["vt_symbol"])
            if sym is None:
                continue
            signals.append(
                Signal(
                    symbol=sym,
                    strength=self.strength,
                    direction=Direction.LONG,
                    timestamp=ts,
                    confidence=float(min(1.0, max(0.0, row["_score"]))),
                    horizon_days=self.forward_days,
                    source="MLSelectorAlpha",
                    rationale=f"rf-score={row['_score']:.3f}",
                )
            )
        for _, row in bottoms.iterrows():
            sym = sym_by_vt.get(row["vt_symbol"])
            if sym is None:
                continue
            signals.append(
                Signal(
                    symbol=sym,
                    strength=self.strength,
                    direction=Direction.SHORT,
                    timestamp=ts,
                    confidence=float(min(1.0, max(0.0, -row["_score"]))),
                    horizon_days=self.forward_days,
                    source="MLSelectorAlpha",
                    rationale=f"rf-score={row['_score']:.3f}",
                )
            )
        return signals
