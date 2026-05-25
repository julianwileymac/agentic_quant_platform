"""Analyzer — natural-language / unstructured-input analysis.

The report's fifth reference application: parse unstructured textual
data (SEC 10-K filings, earnings-call transcripts, news feeds) and
emit a structured dict that agents can consume directly.

Backed by any model that exposes ``analyze(text) -> dict`` (custom
wrappers) or a ``predict(text)`` returning a label / score that the
adapter normalises to ``{"label": str, "score": float, ...}``.

Hugging Face text-classification pipelines wrapped via
:class:`aqp_models.models.huggingface.HuggingFaceTextSignalModel` are
the canonical backing implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp_models.interfaces.base import InterfaceMetadata, PolymorphicInterface


@dataclass(slots=True)
class AnalyzerOutput:
    """Structured output of :meth:`Analyzer.analyze`."""

    payload: dict[str, Any]
    n_documents: int = 1
    metadata: InterfaceMetadata | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "payload": dict(self.payload),
            "n_documents": int(self.n_documents),
            "metadata": self.metadata.to_json() if self.metadata else None,
        }


@register("Analyzer", kind="interface")
class Analyzer(PolymorphicInterface):
    """Polymorphic wrapper for NLP / unstructured-data analysers."""

    interface_kind = "analyzer"
    alias = "analyzer"

    def __init__(
        self,
        *,
        model: Any,
        alias: str | None = None,
        text_column: str = "text",
    ) -> None:
        super().__init__(model=model, alias=alias)
        self._text_column = str(text_column)

    def analyze(self, data: Any, **kwargs: Any) -> AnalyzerOutput:
        started = datetime.utcnow()

        # Native analyze
        if hasattr(self.model, "analyze"):
            payload = self.model.analyze(data, **kwargs)
            if not isinstance(payload, dict):
                payload = {"value": payload}
            n_docs = _count_documents(data)
            return AnalyzerOutput(
                payload=payload,
                n_documents=n_docs,
                metadata=self._build_metadata(
                    started=started, extras={"strategy": "native_analyze"}
                ),
            )

        # Score-bearing predict fallback (FinBERT-style)
        texts = _extract_text_list(data, self._text_column)
        if not texts:
            return AnalyzerOutput(
                payload={"value": None, "n_documents": 0},
                n_documents=0,
                metadata=self._build_metadata(
                    started=started, extras={"strategy": "no_text_found"}
                ),
            )

        frame = _build_text_frame(texts, column=self._text_column)
        try:
            raw = self._delegate_predict(frame, **kwargs)
        except Exception as exc:  # noqa: BLE001
            return AnalyzerOutput(
                payload={"error": str(exc)},
                n_documents=len(texts),
                metadata=self._build_metadata(
                    started=started, extras={"strategy": "delegate_failed"}
                ),
            )

        scores = _coerce_scores(raw)
        payload = {
            "scores": scores.reshape(-1).tolist(),
            "mean_score": float(np.nanmean(scores)) if scores.size else 0.0,
            "n_documents": len(texts),
        }
        return AnalyzerOutput(
            payload=payload,
            n_documents=len(texts),
            metadata=self._build_metadata(
                started=started,
                extras={
                    "strategy": "score_from_predict",
                    "text_column": self._text_column,
                },
            ),
        )

    def supports(self, model: Any) -> bool:
        return hasattr(model, "analyze") or hasattr(model, "predict")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_text_list(data: Any, text_column: str) -> list[str]:
    if isinstance(data, str):
        return [data]
    if isinstance(data, (list, tuple)):
        return [str(x) for x in data if x is not None]
    if isinstance(data, pd.Series):
        return [str(x) for x in data.tolist()]
    if isinstance(data, pd.DataFrame):
        if text_column in data.columns:
            return [str(x) for x in data[text_column].tolist()]
        # First object/string column wins.
        for col in data.columns:
            if data[col].dtype == object:
                return [str(x) for x in data[col].tolist()]
    if isinstance(data, dict):
        if text_column in data:
            return [str(data[text_column])]
        for v in data.values():
            if isinstance(v, str):
                return [v]
    return []


def _count_documents(data: Any) -> int:
    if isinstance(data, str):
        return 1
    if isinstance(data, (list, tuple, pd.Series)):
        return len(data)
    if isinstance(data, pd.DataFrame):
        return int(len(data))
    if isinstance(data, dict):
        return 1
    return 1


def _build_text_frame(texts: list[str], *, column: str) -> pd.DataFrame:
    return pd.DataFrame({column: texts})


def _coerce_scores(raw: Any) -> np.ndarray:
    if isinstance(raw, pd.Series):
        return raw.to_numpy(dtype=float)
    if isinstance(raw, pd.DataFrame):
        return raw.to_numpy(dtype=float)
    return np.asarray(raw, dtype=float)


__all__ = ["AnalyzerOutput", "Analyzer"]
