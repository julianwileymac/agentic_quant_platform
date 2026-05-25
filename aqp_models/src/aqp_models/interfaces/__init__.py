"""Agent-facing polymorphic ML interfaces.

The ``Predictor`` / ``Forecaster`` / ``Classifier`` / ``Segmenter`` /
``Analyzer`` ABCs in this subpackage are the **stable contract** the
agentic layer programs against. Concrete models from
:mod:`aqp_models.models` (tree / torch / huggingface / forecasting / ...)
are wrapped in these interfaces so an LLM agent or RL policy that
issues ``predictor.predict(features)`` does not need to know whether
the underlying implementation is XGBoost, an LSTM, or a Hugging Face
Transformer.

The five interfaces map directly to the five report-mandated agent
patterns:

* :class:`Predictor` — point-in-time value estimation (e.g. next-bar
  return).
* :class:`Forecaster` — multi-step horizon projection (e.g. 20-day
  volatility surface).
* :class:`Classifier` — discrete probability distribution over a
  finite class set (e.g. regime detector).
* :class:`Segmenter` — structural-break / regime-change detection in a
  non-stationary time series.
* :class:`Analyzer` — natural-language / unstructured-input analysis
  returning a structured dict (e.g. sentiment scoring).

Each interface registers under ``kind="interface"`` in the central
``aqp.core.registry`` so the ``data.ml.*`` MCP tools and the frontend
zoo page can enumerate available wrappers without hard-coded lists.
"""
from __future__ import annotations

from aqp_models.interfaces.analyzer import Analyzer, AnalyzerOutput
from aqp_models.interfaces.base import (
    InterfaceKind,
    InterfaceMetadata,
    PolymorphicInterface,
)
from aqp_models.interfaces.classifier import Classifier, ClassDistribution
from aqp_models.interfaces.forecaster import Forecaster, ForecastResult
from aqp_models.interfaces.predictor import Predictor, PredictionResult
from aqp_models.interfaces.segmenter import Segmenter, SegmentBoundary
from aqp_models.interfaces.wrap import list_interface_kinds, wrap_model

__all__ = [
    "Analyzer",
    "AnalyzerOutput",
    "ClassDistribution",
    "Classifier",
    "ForecastResult",
    "Forecaster",
    "InterfaceKind",
    "InterfaceMetadata",
    "PolymorphicInterface",
    "PredictionResult",
    "Predictor",
    "SegmentBoundary",
    "Segmenter",
    "list_interface_kinds",
    "wrap_model",
]
