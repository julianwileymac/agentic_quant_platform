"""AQP Data Lab — the four-mode (EDA / Testing / Evaluation / Simulation)
workspace built on top of the existing :class:`Lab` tenancy entity.

The Data Lab adds no new runtime abstraction. ``GraphSpec`` is a router
schema that :class:`LabRuntime` compiles into a call against one of:

- :class:`aqp.analysis.runtime.AnalysisRuntime` (EDA cell preview).
- A Celery canvas of :class:`AnalysisRuntime.run` calls (Testing).
- A Celery group of parametrised runs + Optuna/Ray sweep controllers
  (Evaluation).
- :class:`aqp.dagster.sandbox.runtime.SandboxRuntime` (Simulation).

This package is intentionally additive: nothing under
``aqp/analysis/``, ``aqp/agents/orchestration/``, ``aqp/rl/``,
``aqp/bots/``, ``aqp/dagster/``, or ``aqp/backtest/`` changes.

Submodules:

- :mod:`aqp.lab.schema` — Pydantic GraphSpec / NodeSpec / EdgeSpec.
- :mod:`aqp.lab.hashing` — canonical-JSON SHA256 content hashing.
- :mod:`aqp.lab.registry` — 35 NodeType records + executor dispatch.
- :mod:`aqp.lab.runtime` — :class:`LabRuntime` and pre-flight checks.
- :mod:`aqp.lab.compiler` — four compile targets (eda / testing /
  evaluation / simulation).
- :mod:`aqp.lab.executors` — per-node-type Python executors.
- :mod:`aqp.lab.ws` — typed envelopes + Redis pub/sub fanout.
- :mod:`aqp.lab.evaluation` — Combinatorial Purged CV + Deflated Sharpe.
- :mod:`aqp.lab.rag` — hybrid retrieval over RagCorpus + pgvector.
"""
from __future__ import annotations

from aqp.lab.hashing import compute_content_hash, snapshot_data_locator
from aqp.lab.schema import (
    EdgeSpec,
    GraphSpec,
    ModeConfig,
    NodeRuntime,
    NodeSpec,
    Port,
    PortDType,
)

__all__ = [
    "EdgeSpec",
    "GraphSpec",
    "ModeConfig",
    "NodeRuntime",
    "NodeSpec",
    "Port",
    "PortDType",
    "compute_content_hash",
    "snapshot_data_locator",
]
