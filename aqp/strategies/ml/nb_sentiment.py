"""Naive Bayes sentiment classifier alpha.

A lightweight bag-of-words Bernoulli/Multinomial NB classifier that
maps news headlines / social posts to directional bias. Built on top
of :class:`aqp.ml.models.naive_bayes.NaiveBayesSentimentModel` so the
classifier itself is a registered AQP model — meaning experiments,
deployments, and the ML test harness can drive it just like any
other registered alpha.

The strategy expects each bar row to optionally include a
``text`` column carrying the latest news headline / sentiment tweet
for that bar. Bars without text are skipped.
"""
from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register(
    "NaiveBayesSentimentAlpha",
    source="research_report_2026",
    category="sentiment",
    kind="strategy",
)
class NaiveBayesSentimentAlpha(IAlphaModel):
    """Bag-of-words NB classifier on per-bar text.

    Parameters
    ----------
    text_column
        Bar column carrying the latest text per symbol.
    train_text_column
        Column carrying training labels (1 = bullish, 0 = bearish).
        Used only when the strategy lazily trains on first call.
    margin_threshold
        Minimum class probability gap required to emit a signal.
    hold_bars
        Forecast horizon.
    """

    def __init__(
        self,
        text_column: str = "text",
        train_text_column: str = "sentiment_label",
        margin_threshold: float = 0.2,
        hold_bars: int = 1,
        model: Any | None = None,
    ) -> None:
        self.text_column = text_column
        self.train_text_column = train_text_column
        self.margin_threshold = float(margin_threshold)
        self.hold_bars = int(hold_bars)
        self._model = model

    def _ensure_fitted(self, sub: pd.DataFrame) -> bool:
        if self._model is not None:
            return True
        if self.train_text_column not in sub.columns or self.text_column not in sub.columns:
            return False
        try:
            from aqp.ml.models.naive_bayes import NaiveBayesSentimentModel
        except Exception:  # noqa: BLE001
            return False
        valid = sub[sub[self.text_column].notna() & sub[self.train_text_column].notna()]
        if len(valid) < 20:
            return False
        nb = NaiveBayesSentimentModel()
        nb.fit_texts(
            valid[self.text_column].astype(str).tolist(),
            valid[self.train_text_column].astype(int).tolist(),
        )
        self._model = nb
        return True

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: Sequence[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty or self.text_column not in bars.columns:
            return []
        universe_set = {s.vt_symbol for s in universe}
        signals: list[Signal] = []
        now = context.get("current_time")
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if not self._ensure_fitted(sub):
                continue
            assert self._model is not None
            text = sub[self.text_column].iloc[-1]
            if pd.isna(text) or not str(text).strip():
                continue
            probs = self._model.predict_proba_texts([str(text)])[0]
            p_long = float(probs[1]) if len(probs) > 1 else 0.0
            p_short = float(probs[0])
            margin = p_long - p_short
            if abs(margin) < self.margin_threshold:
                continue
            direction = Direction.LONG if margin > 0 else Direction.SHORT
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt_symbol),
                    strength=float(min(abs(margin), 1.0)),
                    direction=direction,
                    timestamp=now or sub["timestamp"].iloc[-1],
                    confidence=float(max(p_long, p_short)),
                    horizon_days=self.hold_bars,
                    source="NaiveBayesSentimentAlpha",
                    rationale=(
                        f"text='{str(text)[:48]}…' p_long={p_long:.2f} "
                        f"p_short={p_short:.2f}"
                    ),
                )
            )
        return signals
