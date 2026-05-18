"""Concrete DataMCP tool implementations grouped by domain.

Each submodule registers a handful of :class:`DataMCPTool` subclasses
via the :func:`aqp.data.mcp.registry.register_data_mcp_tool`
decorator. Importing this package transitively registers every tool.
"""
from __future__ import annotations

from aqp.data.mcp.tools import (  # noqa: F401  (side-effect imports)
    agents,
    alphas,
    arbitrage,
    aspects,
    automation,
    backtests,
    brokers,
    catalog,
    datahub,
    discovery,
    entities,
    experiments,
    futures,
    iceberg,
    identity,
    instruments,
    kubernetes,
    namespace_policy,
    optimal_control,
    orchestration,
    ownership,
    pipelines,
    pricing,
    rl,
    sinks,
    sources,
    strategies,
    strategy_config,
    streaming,
    tenancy,
    terraform,
    tests,
    vector,
)

__all__: list[str] = []
