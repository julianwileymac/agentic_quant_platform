"""ML-driven alpha strategies covered in the 2026 research report.

Three concrete strategies — SVM for FX trend-following, ANN for
crypto decile classification, and Naive Bayes for news sentiment.
Each strategy bakes in its own feature engineering and consumes a
trained model that travels with the strategy instance (via the
``model`` argument, or auto-trained from the provided bars on first
call).

Strategies registered:

- :class:`SVMFXTrendAlpha`
- :class:`ANNCryptoDecileAlpha`
- :class:`NaiveBayesSentimentAlpha`
"""
from __future__ import annotations

from aqp.strategies.ml.ann_crypto_decile import ANNCryptoDecileAlpha
from aqp.strategies.ml.nb_sentiment import NaiveBayesSentimentAlpha
from aqp.strategies.ml.svm_fx_trend import SVMFXTrendAlpha

__all__ = [
    "ANNCryptoDecileAlpha",
    "NaiveBayesSentimentAlpha",
    "SVMFXTrendAlpha",
]
