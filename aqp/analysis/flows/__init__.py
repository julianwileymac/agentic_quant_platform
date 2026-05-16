"""Flow modules for the AQP analysis umbrella.

Importing this package triggers every concrete flow registration via
the :func:`aqp.analysis.registry.register_analysis_flow` decorator.
The lab UI's ``GET /analysis/flows`` lists them; the runtime's
:class:`AnalysisRuntime` dispatches to them.

Adding a new flow module = adding it to the import block below.
Optional dependencies are handled inside each module — failures to
import a single flow module must NOT break the package.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _safe_import(module: str) -> None:
    try:
        __import__(f"aqp.analysis.flows.{module}")
    except Exception:  # noqa: BLE001
        logger.debug("analysis.flows.%s import failed", module, exc_info=True)


for _name in (
    "profiling",
    "distribution",
    "outlier",
    "imputation",
    "regression",
    "time_series",
    "optimal_control",  # loaded before derivatives so the latter can import LucicTseFlowParams
    "derivatives",
    "portfolio",
    "factors",
    "microstructure",
):
    _safe_import(_name)


__all__: list[str] = []
