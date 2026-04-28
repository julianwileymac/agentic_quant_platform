"""CrewAI tool: score sentiment over a text window using FinBERT (or fallback)."""
from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class SentimentScoreInput(BaseModel):
    texts: list[str] = Field(..., min_length=1)
    model: str | None = Field(
        default=None,
        description="HuggingFace model id; falls back to ``settings.sentiment_model``.",
    )


class SentimentScoreTool(BaseTool):
    name: str = "sentiment_score"
    description: str = (
        "Score one or more texts as {positive, negative, neutral} probabilities. "
        "Defaults to FinBERT (yiyanghkust/finbert-tone)."
    )
    args_schema: type[BaseModel] = SentimentScoreInput

    def _run(self, texts: list[str], model: str | None = None) -> str:  # type: ignore[override]
        from aqp.config import settings

        model_id = model or settings.sentiment_model
        try:
            from transformers import pipeline

            pipe = pipeline("text-classification", model=model_id, top_k=None)
            results = pipe(texts, truncation=True)
            return _format(texts, results)
        except Exception as exc:  # noqa: BLE001
            return _heuristic(texts, model_id, exc)


def _format(texts: list[str], results: Any) -> str:
    import json

    out: list[dict[str, Any]] = []
    for text, scores in zip(texts, results, strict=False):
        score_map = {s["label"].lower(): float(s["score"]) for s in scores}
        out.append({"text": text[:120], **score_map})
    return json.dumps(out, indent=2)


def _heuristic(texts: list[str], model_id: str, exc: Exception) -> str:
    import json

    # Lightweight lexical fallback so the tool still returns something
    # when the model isn't installed.
    pos_words = {"beat", "growth", "expand", "approve", "record", "strong", "raise", "outperform"}
    neg_words = {"miss", "loss", "decline", "recall", "lawsuit", "fraud", "delay", "underperform", "downgrade"}
    out: list[dict[str, Any]] = []
    for t in texts:
        toks = (t or "").lower().split()
        p = sum(1 for w in toks if w in pos_words)
        n = sum(1 for w in toks if w in neg_words)
        total = max(p + n, 1)
        out.append(
            {
                "text": t[:120],
                "positive": p / total,
                "negative": n / total,
                "neutral": max(0.0, 1 - (p + n) / max(len(toks), 1)),
                "_fallback": True,
                "_fallback_reason": f"{type(exc).__name__}: {exc}",
                "_fallback_model": model_id,
            }
        )
    return json.dumps(out, indent=2)


__all__ = ["SentimentScoreTool"]
