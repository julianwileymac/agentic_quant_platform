"""Smoke tests for the Analyzer interface."""
from __future__ import annotations

from aqp_models.interfaces import Analyzer


class _NativeAnalyzer:
    def analyze(self, data: str) -> dict[str, float | int]:
        return {"value": float(len(data)), "n_documents": 1}


def test_native_analyze_returns_dict() -> None:
    wrapper = Analyzer(model=_NativeAnalyzer())
    out = wrapper.analyze("hello world")
    assert out.payload["value"] == float(len("hello world"))
    assert out.metadata.extras["strategy"] == "native_analyze"


def test_no_text_found_returns_n_documents_zero() -> None:
    class _ScoreModel:
        def predict(self, _frame):  # noqa: ARG002
            return [0.5]

    wrapper = Analyzer(model=_ScoreModel())
    out = wrapper.analyze({})
    assert out.n_documents == 0
