"""Phase 2: unified execution surface built on :class:`DomainOrder`.

Public surface for the legacy <-> domain bridge, the amendment manager,
the contingency-graph state machine, and the execution-report dispatcher.

The legacy ``IBrokerage`` interface in :mod:`aqp.core.interfaces` still
defines the ``submit_order(OrderRequest) -> OrderData`` shape used by
backtests + the paper session today. Phase 2 adds a parallel surface
that operates on :class:`DomainOrder`; the bridge in
:class:`LegacyDomainOrderAdapter` translates both ways so consumers
can migrate one at a time without breaking back-compat.
"""
from __future__ import annotations

from aqp.trading.execution.amendment import (
    AmendmentManager,
    AmendmentRequest,
    AmendmentResult,
    AmendmentRouting,
)
from aqp.trading.execution.contingency import (
    ContingencyAction,
    ContingencyManager,
    ContingencyState,
)
from aqp.trading.execution.execution_report import (
    ExecutionReport,
    ExecutionReportDispatcher,
    ReportKind,
)
from aqp.trading.execution.legacy_adapter import (
    LegacyDomainOrderAdapter,
    domain_order_from_order_request,
    order_data_from_domain_order,
)
from aqp.trading.execution.protocol import (
    IDomainBrokerage,
)

__all__ = [
    "AmendmentManager",
    "AmendmentRequest",
    "AmendmentResult",
    "AmendmentRouting",
    "ContingencyAction",
    "ContingencyManager",
    "ContingencyState",
    "ExecutionReport",
    "ExecutionReportDispatcher",
    "IDomainBrokerage",
    "LegacyDomainOrderAdapter",
    "ReportKind",
    "domain_order_from_order_request",
    "order_data_from_domain_order",
]
