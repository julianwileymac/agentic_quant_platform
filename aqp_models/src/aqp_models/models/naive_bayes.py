"""Naive Bayes sentiment classifier model.

Registered as ``NaiveBayesSentimentModel`` (``kind="model"``). Wraps
sklearn's :class:`sklearn.naive_bayes.MultinomialNB` plus a
:class:`sklearn.feature_extraction.text.CountVectorizer` so the
fit/predict cycle takes raw text and returns probabilities.

Why a registered model? AQP-native experiments / deployments / the
``/ml/test/*`` workbench all reference models by their registry name
+ class. Wrapping the NB classifier this way means the new
:class:`aqp.strategies.ml.nb_sentiment.NaiveBayesSentimentAlpha` can
just say "load the registered ``NaiveBayesSentimentModel`` deployment"
and the existing ML test surfaces light up automatically.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register

try:  # pragma: no cover - import-time check
    from sklearn.feature_extraction.text import CountVectorizer  # type: ignore[import-not-found]
    from sklearn.naive_bayes import MultinomialNB  # type: ignore[import-not-found]

    _SKLEARN_AVAILABLE = True
except Exception:  # noqa: BLE001
    CountVectorizer = None  # type: ignore[assignment]
    MultinomialNB = None  # type: ignore[assignment]
    _SKLEARN_AVAILABLE = False


@register("NaiveBayesSentimentModel", kind="model", source="research_report_2026")
class NaiveBayesSentimentModel:
    """Bag-of-words Naive Bayes sentiment classifier.

    Parameters
    ----------
    min_df
        Minimum document frequency for the count vectoriser.
    ngram_range
        N-gram range, passed through to the vectoriser.
    alpha
        Laplace smoothing parameter for the NB likelihood.

    Notes
    -----
    The instance exposes ``fit_texts`` / ``predict_proba_texts``
    for direct use from strategy code, plus the standard
    ``fit``/``predict`` AQP-Model contract for cases where the model
    is wired into a ``DatasetH``-driven experiment (the dataset's
    ``text`` column is used).
    """

    def __init__(
        self,
        min_df: int = 1,
        ngram_range: tuple[int, int] = (1, 1),
        alpha: float = 1.0,
    ) -> None:
        self.min_df = int(min_df)
        self.ngram_range = tuple(int(x) for x in ngram_range)  # type: ignore[assignment]
        self.alpha = float(alpha)
        self._vectorizer: Any = None
        self._classifier: Any = None
        self.classes_: list[int] = []

    def fit_texts(self, texts: list[str], labels: list[int]) -> NaiveBayesSentimentModel:
        if not _SKLEARN_AVAILABLE:
            raise RuntimeError("scikit-learn not installed — NaiveBayesSentimentModel inert")
        if not texts:
            raise ValueError("texts must be non-empty")
        self._vectorizer = CountVectorizer(
            min_df=self.min_df, ngram_range=self.ngram_range
        )
        X = self._vectorizer.fit_transform(texts)
        self._classifier = MultinomialNB(alpha=self.alpha)
        self._classifier.fit(X, np.asarray(labels))
        self.classes_ = list(self._classifier.classes_)
        return self

    def predict_proba_texts(self, texts: list[str]) -> np.ndarray:
        if self._classifier is None or self._vectorizer is None:
            raise RuntimeError("Model not fit — call fit_texts first")
        X = self._vectorizer.transform(texts)
        return self._classifier.predict_proba(X)

    # AQP-Model contract for experiment / deployment integration.

    def fit(self, dataset: Any, reweighter: Any | None = None) -> NaiveBayesSentimentModel:
        df = self._coerce(dataset)
        texts = df["text"].astype(str).tolist()
        labels = df["label"].astype(int).tolist()
        return self.fit_texts(texts, labels)

    def predict(self, dataset: Any, segment: str | slice = "test") -> pd.Series:
        df = self._coerce(dataset, segment=segment)
        texts = df["text"].astype(str).tolist()
        if not texts:
            return pd.Series(dtype=float)
        probs = self.predict_proba_texts(texts)
        # Return P(class=positive) as the scalar prediction.
        if 1 in self.classes_:
            pos_idx = self.classes_.index(1)
        else:
            pos_idx = probs.shape[1] - 1
        return pd.Series(probs[:, pos_idx], index=df.index)

    @staticmethod
    def _coerce(dataset: Any, *, segment: str | slice = "train") -> pd.DataFrame:
        if isinstance(dataset, pd.DataFrame):
            return dataset
        if hasattr(dataset, "to_frame"):
            return dataset.to_frame(segment=segment)
        raise TypeError(
            f"NaiveBayesSentimentModel expects a DataFrame-like dataset, got {type(dataset)!r}"
        )
