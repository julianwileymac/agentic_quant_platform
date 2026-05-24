"""Embedding provider abstraction.

Supports:
 - OpenAI-compatible API (works with local vLLM, Ollama, TEI, etc.)
 - Sentence-transformers (local CPU/GPU)
 - Deterministic fallback for testing
"""

from __future__ import annotations

import hashlib
import os
from typing import Any


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def deterministic_embedding(text: str, dim: int = 384) -> list[float]:
    """Hash-based deterministic embedding for testing without a model."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for idx in range(dim):
        byte_val = digest[idx % len(digest)]
        values.append((byte_val / 255.0) * 2 - 1)
    return values


class EmbeddingProvider:
    """Unified embedding interface backed by different providers."""

    def __init__(
        self,
        provider: str | None = None,
        model_name: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        dimension: int = 384,
    ):
        self.provider = provider or _env("EMBEDDING_PROVIDER", "deterministic")
        self.model_name = model_name or _env("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.api_base = api_base or _env("EMBEDDING_API_BASE", "")
        self.api_key = api_key or _env("EMBEDDING_API_KEY", "")
        self.dimension = dimension
        self._model: Any = None

    def _load_sentence_transformer(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self.dimension = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts and return vectors."""
        if self.provider == "deterministic":
            return [deterministic_embedding(t, dim=self.dimension) for t in texts]

        if self.provider == "sentence_transformers":
            model = self._load_sentence_transformer()
            embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
            return [e.tolist() for e in embeddings]

        if self.provider in ("openai", "openai_compatible"):
            return self._openai_embed(texts)

        raise ValueError(f"Unknown embedding provider: {self.provider}")

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text."""
        return self.embed_texts([text])[0]

    def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        """Call an OpenAI-compatible embeddings endpoint."""
        import requests

        base = self.api_base.rstrip("/")
        url = f"{base}/embeddings" if "/v1" in base else f"{base}/v1/embeddings"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        batch_size = 32
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = requests.post(
                url,
                headers=headers,
                json={"input": batch, "model": self.model_name},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            data.sort(key=lambda x: x["index"])
            all_embeddings.extend([d["embedding"] for d in data])

        if all_embeddings:
            self.dimension = len(all_embeddings[0])

        return all_embeddings


def get_default_provider() -> EmbeddingProvider:
    """Get a provider configured from environment variables."""
    return EmbeddingProvider()
