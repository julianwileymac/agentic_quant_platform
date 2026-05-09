"""Unified analysis umbrella for AQP.

A new top-level package that consolidates statistical, distribution,
time-series, derivatives, portfolio, regression, and outlier
analytics behind a hash-locked :class:`AnalysisSpec` and a single
:class:`AnalysisRuntime` executor — mirroring the
:mod:`aqp.rl` / :mod:`aqp.bots` / :mod:`aqp.agents` patterns.

Three architectural layers:

1. :mod:`aqp.analysis.spec` declares :class:`AnalysisSpec`,
   :class:`AnalysisStep`, and :class:`FlowRef` (Pydantic + SHA256
   canonical hash).
2. :mod:`aqp.analysis.registry` owns the :func:`register_analysis_flow`
   decorator + :func:`persist_spec` / :func:`replay_spec_version`.
3. :mod:`aqp.analysis.runtime` owns :class:`AnalysisRuntime`, the only
   sanctioned executor — Celery (`aqp.tasks.analysis_flow_tasks`)
   and the REST router (`aqp.api.routes.analysis`) wrap it.

Every flow registers via the decorator under a namespaced key
(``"distribution.shapiro_wilk"``, ``"derivatives.bsm"``, …) so
the lab UI can group them into tabs without hard-coding categories.

Iceberg outputs land under ``aqp_gold_analysis_<namespace>`` via
:func:`aqp.data.iceberg_catalog.append_arrow` with
``medallion_layer="gold"`` and a :class:`BusinessMetadata` block —
the canonical AQP data-write path.
"""
from __future__ import annotations

from aqp.analysis.base import (
    AnalysisFlow,
    FlowContext,
    FlowDescriptor,
    FlowParams,
    FlowResult,
    FlowSchema,
)
from aqp.analysis.registry import (
    FLOW_REGISTRY,
    add_spec,
    get_analysis_spec,
    list_analysis_flows,
    list_analysis_specs,
    persist_spec,
    register_analysis_flow,
    replay_spec_version,
    resolve_flow,
    run_flow,
)
from aqp.analysis.runtime import AnalysisRunResult, AnalysisRuntime, runtime_for
from aqp.analysis.spec import (
    AnalysisSpec,
    AnalysisSpecKind,
    AnalysisStep,
    DatasetRef,
    FlowRef,
    load_specs_from_dir,
)

# Auto-import flow modules so the registry populates on first import.
from aqp.analysis import flows  # noqa: F401  (side-effects: register flows)


__all__ = [
    "AnalysisFlow",
    "AnalysisRunResult",
    "AnalysisRuntime",
    "AnalysisSpec",
    "AnalysisSpecKind",
    "AnalysisStep",
    "DatasetRef",
    "FLOW_REGISTRY",
    "FlowContext",
    "FlowDescriptor",
    "FlowParams",
    "FlowRef",
    "FlowResult",
    "FlowSchema",
    "add_spec",
    "get_analysis_spec",
    "list_analysis_flows",
    "list_analysis_specs",
    "load_specs_from_dir",
    "persist_spec",
    "register_analysis_flow",
    "replay_spec_version",
    "resolve_flow",
    "run_flow",
    "runtime_for",
]
