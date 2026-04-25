"""qlib-style processor adding sentiment as a feature column.

Plugs into :class:`aqp.ml.handler.DataHandlerLP` exactly like the
built-in processors in :mod:`aqp.ml.processors`. The processor:

1. Reads a configurable ``text_col`` from each row (default
   ``"news_title"``), defaults to an empty string when missing.
2. Scores each row with :class:`SentimentScorer`.
3. Writes a new column (default ``"sentiment"``) into the handler's
   panel.

When the text column doesn't exist we skip gracefully so the same
pipeline works on panels that don't have news joined in (it just
doesn't add sentiment).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.core.registry import register
from aqp.ml.applications.sentiment.scorer import SentimentScorer, get_scorer
from aqp.ml.processors import Processor

logger = logging.getLogger(__name__)


@register("SentimentProcessor")
class SentimentProcessor(Processor):
    """Score a text column and append a ``(feature, sentiment)`` column.

    Parameters
    ----------
    text_col:
        Source column name. ``"news_title"`` by default.
    output_col:
        New column name. ``"sentiment"`` by default.
    fields_group:
        When the handler uses a two-level ``("feature" | "label", col)``
        MultiIndex we emit the new column under ``fields_group``.
        ``"feature"`` by default.
    model_name:
        Optional override for the HuggingFace model.
    """

    fit_required: bool = False

    def __init__(
        self,
        text_col: str = "news_title",
        output_col: str = "sentiment",
        fields_group: str = "feature",
        model_name: str | None = None,
    ) -> None:
        self.text_col = text_col
        self.output_col = output_col
        self.fields_group = fields_group
        self.model_name = model_name
        self._scorer: SentimentScorer | None = None

    def _ensure_scorer(self) -> SentimentScorer:
        if self._scorer is None:
            self._scorer = get_scorer(self.model_name)
        return self._scorer

    def __call__(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        texts = self._extract_texts(df)
        if texts is None:
            # Column absent — skip without raising.
            return df
        try:
            scores = self._ensure_scorer().score(texts)
        except Exception as exc:
            logger.warning("sentiment processor skipped (%s)", exc)
            return df

        out = df.copy()
        if isinstance(out.columns, pd.MultiIndex):
            out[(self.fields_group, self.output_col)] = scores
        else:
            out[self.output_col] = scores
        return out

    # ------------------------------------------------------------------

    def _extract_texts(self, df: pd.DataFrame) -> list[str] | None:
        """Pull the text column out of a flat or MultiIndex frame."""
        if isinstance(df.columns, pd.MultiIndex):
            candidates = [
                c for c in df.columns if c[-1] == self.text_col
            ]
            if not candidates:
                return None
            return df[candidates[0]].fillna("").astype(str).tolist()
        if self.text_col not in df.columns:
            return None
        return df[self.text_col].fillna("").astype(str).tolist()
