"""Concrete DataMCP tool implementations grouped by domain.

Each submodule registers a handful of :class:`DataMCPTool` subclasses
via the :func:`aqp.data.mcp.registry.register_data_mcp_tool`
decorator. Importing this package transitively registers every tool.
"""
from __future__ import annotations

from aqp.data.mcp.tools import (  # noqa: F401  (side-effect imports)
    account,
    agents,
    alphas,
    arbitrage,
    aspects,
    assistants,
    automation,
    backtests,
    brokers,
    catalog,
    cloudflare,
    datahub,
    discovery,
    docs,
    entities,
    experiments,
    futures,
    hudi,
    iceberg,
    identity,
    instruments,
    kubernetes,
    lab,
    lineage_graph,
    ml,
    namespace_policy,
    oauth_connections,
    observability,
    optimal_control,
    orchestration,
    ownership,
    phoenix,
    pipelines,
    pricing,
    questdb,
    research_papers,
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
