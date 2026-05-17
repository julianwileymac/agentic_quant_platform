"""Registry of every :class:`DataMCPTool`.

Tools self-register at import time. Both transports (in-process bridge
and external MCP server) read from :data:`DATA_MCP_TOOLS` so the
catalog always stays consistent.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.data.mcp.base import DataMCPTool

logger = logging.getLogger(__name__)


DATA_MCP_TOOLS: dict[str, type[DataMCPTool]] = {}


def register_data_mcp_tool(cls: type[DataMCPTool]) -> type[DataMCPTool]:
    """Decorator that registers a :class:`DataMCPTool` subclass.

    .. code-block:: python

        @register_data_mcp_tool
        class BrowseCatalogTool(DataMCPTool):
            name = "data.catalog.browse"
            ...
    """
    if not issubclass(cls, DataMCPTool):
        raise TypeError(f"{cls!r} must subclass DataMCPTool")
    name = (cls.name or "").strip()
    if not name:
        raise ValueError(f"{cls.__name__} must set ``name``")
    if name in DATA_MCP_TOOLS and DATA_MCP_TOOLS[name] is not cls:
        logger.debug("Replacing DataMCPTool registration for %s", name)
    DATA_MCP_TOOLS[name] = cls
    return cls


def get_data_mcp_tool(name: str) -> DataMCPTool:
    """Instantiate a registered tool by name.

    Returns a new instance per call so tools that hold short-lived
    state (rate limiters, caches) don't leak across sessions.
    """
    if name not in DATA_MCP_TOOLS:
        raise KeyError(
            f"unknown DataMCPTool {name!r}; registered: {sorted(DATA_MCP_TOOLS)}"
        )
    return DATA_MCP_TOOLS[name]()


def list_data_mcp_tools() -> list[dict[str, Any]]:
    """Return descriptors for every registered tool, sorted by name.

    Used by the unified Data Hub UI catalog tab and the MCP server
    discovery endpoint.
    """
    out: list[dict[str, Any]] = []
    for name in sorted(DATA_MCP_TOOLS):
        cls = DATA_MCP_TOOLS[name]
        out.append(cls.to_mcp_tool_descriptor())
    return out


__all__ = [
    "DATA_MCP_TOOLS",
    "get_data_mcp_tool",
    "list_data_mcp_tools",
    "register_data_mcp_tool",
]
