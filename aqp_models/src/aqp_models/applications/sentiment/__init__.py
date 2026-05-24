"""FinGPT-sentiment integration (scorer + processor + datasets).

Surface summary:

- :class:`SentimentScorer` — batch sentiment scoring over HuggingFace pipeline.
- :func:`get_scorer` — singleton factory used by the trader crew's news tool.
- :class:`SentimentProcessor` — qlib-style processor for :class:`DataHandlerLP`.
- :func:`register_datasets` — register FinGPT instruction-tuning dataset ids.
"""
from __future__ import annotations

from aqp_models.applications.sentiment.datasets import (
    FINGPT_DATASETS,
    SentimentDatasetSpec,
    register_datasets,
)
from aqp_models.applications.sentiment.processor import SentimentProcessor
from aqp_models.applications.sentiment.scorer import SentimentScorer, get_scorer

__all__ = [
    "FINGPT_DATASETS",
    "SentimentDatasetSpec",
    "SentimentProcessor",
    "SentimentScorer",
    "get_scorer",
    "register_datasets",
]
