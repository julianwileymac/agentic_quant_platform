"""Tests for :class:`NaiveBayesSentimentAlpha` + the NB model."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

pytest.importorskip("sklearn")

from aqp.core.types import Direction, Symbol  # noqa: E402
from aqp_models.models.naive_bayes import NaiveBayesSentimentModel  # noqa: E402
from aqp.strategies.ml.nb_sentiment import NaiveBayesSentimentAlpha  # noqa: E402


def _bars(texts: list[str], labels: list[int]) -> pd.DataFrame:
    rows = []
    n = len(texts)
    for i in range(n):
        rows.append(
            {
                "vt_symbol": "AAPL.NASDAQ",
                "timestamp": datetime(2024, 1, 1) + timedelta(days=i),
                "close": 100.0,
                "text": texts[i],
                "sentiment_label": labels[i],
            }
        )
    return pd.DataFrame(rows)


def test_registry_entry_strategy() -> None:
    from aqp.core.registry import resolve

    assert resolve("NaiveBayesSentimentAlpha") is NaiveBayesSentimentAlpha


def test_registry_entry_model() -> None:
    from aqp.core.registry import resolve

    assert resolve("NaiveBayesSentimentModel") is NaiveBayesSentimentModel


def test_nb_model_fit_then_predict() -> None:
    nb = NaiveBayesSentimentModel()
    texts = (
        ["great earnings beat", "record profit", "strong guidance"] * 8
        + ["fraud allegations", "huge miss", "bankruptcy filed"] * 8
    )
    labels = [1] * 24 + [0] * 24
    nb.fit_texts(texts, labels)
    probs = nb.predict_proba_texts(["record profit"])[0]
    assert probs.sum() == pytest.approx(1.0, rel=1e-6)
    # Positive headline should lean bullish (class 1).
    assert probs[1] > probs[0]


def test_strategy_skips_when_no_text_column() -> None:
    bars = pd.DataFrame(
        {
            "vt_symbol": ["AAPL.NASDAQ"],
            "timestamp": [datetime(2024, 1, 1)],
            "close": [100.0],
        }
    )
    alpha = NaiveBayesSentimentAlpha()
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("AAPL.NASDAQ")],
        context={},
    )
    assert signals == []


def test_strategy_trains_and_emits_signal() -> None:
    texts = (
        ["positive guidance"] * 20
        + ["negative outlook"] * 20
        + ["positive guidance"]  # current bar
    )
    labels = [1] * 20 + [0] * 20 + [1]
    bars = _bars(texts, labels)
    alpha = NaiveBayesSentimentAlpha(margin_threshold=0.0)
    signals = alpha.generate_signals(
        bars=bars,
        universe=[Symbol.parse("AAPL.NASDAQ")],
        context={},
    )
    # Last text is "positive guidance" → expect long signal.
    assert any(s.direction is Direction.LONG for s in signals)
