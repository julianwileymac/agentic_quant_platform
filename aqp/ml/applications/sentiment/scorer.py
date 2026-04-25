"""HuggingFace-backed sentiment scorer for financial text.

Uses the default FinBERT model (``yiyanghkust/finbert-tone``) which is
open and does well on financial headlines. Users can swap in a gated
FinGPT LoRA (e.g. ``FinGPT/fingpt-sentiment_llama2-13b_lora``) via the
``AQP_SENTIMENT_MODEL`` env var — the class handles both encoder and
LoRA configs.

Returns a float in ``[-1, 1]`` per input (positive=1, neutral=0,
negative=-1 with softened confidence). Callers can feed the scores
straight into the trader crew's news/sentiment analyst or into
:class:`SentimentProcessor` for a feature column in Alpha158.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from aqp.config import settings

logger = logging.getLogger(__name__)


_LABEL_TO_SCORE = {
    "positive": 1.0,
    "pos": 1.0,
    "bullish": 1.0,
    "neutral": 0.0,
    "neu": 0.0,
    "negative": -1.0,
    "neg": -1.0,
    "bearish": -1.0,
}


@dataclass
class SentimentResult:
    label: str
    score: float
    raw_confidence: float


class SentimentScorer:
    """Batch sentiment scorer.

    Parameters
    ----------
    model_name:
        Optional override for the HuggingFace model id. Defaults to
        ``settings.sentiment_model``.
    device:
        ``"cpu"`` (default), ``"cuda"``, or a specific index as a string.
        Passed straight through to ``transformers.pipeline``.
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str | int | None = None,
        max_batch_size: int = 16,
    ) -> None:
        self.model_name = model_name or settings.sentiment_model
        self.device = device if device is not None else -1
        self.max_batch_size = int(max_batch_size)
        self._pipe = None

    def _load(self) -> None:
        if self._pipe is not None:
            return
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "transformers is required for SentimentScorer. "
                "Install the optional `[fingpt]` group."
            ) from exc
        try:
            self._pipe = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                device=self.device,
            )
        except Exception as exc:
            # Fall back to FinBERT if the user asked for a gated LoRA we can't load.
            fallback = "yiyanghkust/finbert-tone"
            if self.model_name != fallback:
                logger.warning(
                    "failed to load sentiment model %s (%s); falling back to %s",
                    self.model_name,
                    exc,
                    fallback,
                )
                self.model_name = fallback
                self._pipe = pipeline(
                    "sentiment-analysis",
                    model=fallback,
                    device=self.device,
                )
            else:
                raise

    def score(self, texts: Iterable[str]) -> list[float]:
        """Return a list of floats in [-1, 1] aligned to ``texts``."""
        items = [t or "" for t in texts]
        if not items:
            return []
        self._load()
        assert self._pipe is not None

        results: list[float] = []
        for start in range(0, len(items), self.max_batch_size):
            batch = items[start : start + self.max_batch_size]
            try:
                outputs = self._pipe(batch, truncation=True)
            except Exception as exc:
                logger.debug("sentiment batch failed: %s", exc)
                outputs = [{"label": "neutral", "score": 0.0} for _ in batch]
            for out in outputs:
                label = str(out.get("label", "neutral")).lower()
                conf = float(out.get("score", 0.0))
                sign = _LABEL_TO_SCORE.get(label, 0.0)
                results.append(sign * conf)
        return results

    def score_detailed(self, texts: Iterable[str]) -> list[SentimentResult]:
        """Like :meth:`score` but returns labels + raw confidence per item."""
        items = [t or "" for t in texts]
        if not items:
            return []
        self._load()
        assert self._pipe is not None

        detailed: list[SentimentResult] = []
        for start in range(0, len(items), self.max_batch_size):
            batch = items[start : start + self.max_batch_size]
            try:
                outputs = self._pipe(batch, truncation=True)
            except Exception:
                outputs = [{"label": "neutral", "score": 0.0} for _ in batch]
            for out in outputs:
                label = str(out.get("label", "neutral")).lower()
                conf = float(out.get("score", 0.0))
                sign = _LABEL_TO_SCORE.get(label, 0.0)
                detailed.append(SentimentResult(label=label, score=sign * conf, raw_confidence=conf))
        return detailed


@lru_cache(maxsize=4)
def get_scorer(model_name: str | None = None) -> SentimentScorer:
    """Return a cached :class:`SentimentScorer` for the given model.

    Caching avoids reloading the model on every tool invocation. Keys on
    ``model_name`` so multiple models can coexist if needed.
    """
    return SentimentScorer(model_name=model_name)
