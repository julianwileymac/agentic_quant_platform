"""Quick text-embedding and sentiment helpers (HuggingFace / FinBERT)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class QuickSentimentResult:
    model_name: str
    n_inputs: int
    scores: list[float] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    score_mean: float = 0.0
    score_std: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


@dataclass
class QuickEmbedResult:
    model_name: str
    n_inputs: int
    embedding_dim: int
    embeddings: np.ndarray | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "n_inputs": self.n_inputs,
            "embedding_dim": self.embedding_dim,
            "embeddings": (
                self.embeddings.tolist() if self.embeddings is not None else None
            ),
        }


def quick_finbert_sentiment(
    texts: list[str],
    *,
    model_name: str | None = None,
    device: int = -1,
    batch_size: int = 16,
) -> QuickSentimentResult:
    """Score a list of strings with FinBERT."""
    try:
        from transformers import pipeline
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "transformers is not installed. Install the `ml-transformers` extra."
        ) from exc
    from aqp.config import settings

    name = model_name or settings.hf_finbert_model or "ProsusAI/finbert"
    pipe = pipeline(
        "text-classification",
        model=name,
        device=device,
    )
    if not texts:
        return QuickSentimentResult(model_name=name, n_inputs=0)
    raw = pipe([str(t) for t in texts], batch_size=batch_size, truncation=True)
    scores: list[float] = []
    labels: list[str] = []
    for item in raw:
        if isinstance(item, list):
            item = item[0] if item else {}
        label = str(item.get("label", "")).lower()
        score = float(item.get("score", 0.0))
        signed = score if label.startswith("pos") or label.endswith("_2") else (
            -score if label.startswith("neg") or label.endswith("_0") else 0.0
        )
        scores.append(signed)
        labels.append(label)
    arr = np.asarray(scores, dtype=float)
    return QuickSentimentResult(
        model_name=name,
        n_inputs=int(len(texts)),
        scores=scores,
        labels=labels,
        score_mean=float(arr.mean()) if arr.size else 0.0,
        score_std=float(arr.std()) if arr.size else 0.0,
    )


def quick_text_embed(
    texts: list[str],
    *,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    batch_size: int = 32,
) -> QuickEmbedResult:
    """Embed a list of strings via sentence-transformers."""
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "sentence-transformers is not installed. Install the `agents-rag` extra."
        ) from exc
    if not texts:
        return QuickEmbedResult(model_name=model_name, n_inputs=0, embedding_dim=0)
    model = SentenceTransformer(model_name)
    embeddings = model.encode(
        [str(t) for t in texts], batch_size=batch_size, show_progress_bar=False
    )
    arr = np.asarray(embeddings, dtype=np.float32)
    return QuickEmbedResult(
        model_name=model_name,
        n_inputs=int(len(texts)),
        embedding_dim=int(arr.shape[1] if arr.ndim == 2 else 0),
        embeddings=arr,
    )


__all__ = [
    "QuickEmbedResult",
    "QuickSentimentResult",
    "quick_finbert_sentiment",
    "quick_text_embed",
]
