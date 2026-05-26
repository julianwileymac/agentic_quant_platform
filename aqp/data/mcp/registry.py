"""Registry of every :class:`DataMCPTool`.

Tools self-register at import time. Both transports (in-process bridge
and external MCP server) read from :data:`DATA_MCP_TOOLS` so the
catalog always stays consistent.

Phase 5 §8.4 (RESTRUCTURING_PLAN.md): every registered tool also
records a content-hash of its descriptor so AgentRuntime can persist
``mcp_tool_descriptor_hashes`` on every run, and so the MCP server
can snapshot the catalog into ``mcp_tool_versions`` on boot. The hash
is the SHA-256 of the canonical-JSON form of
``DataMCPTool.to_mcp_tool_descriptor()``; see
:func:`compute_descriptor_hash` below.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from aqp.data.mcp.base import DataMCPTool

logger = logging.getLogger(__name__)


DATA_MCP_TOOLS: dict[str, type[DataMCPTool]] = {}
# Phase 5 §8.4 — name -> sha256 of the canonical-JSON descriptor.
# Populated by :func:`register_data_mcp_tool` so callers don't need
# to re-derive it on every introspection request.
DATA_MCP_TOOL_HASHES: dict[str, str] = {}


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
    # Phase 5 §8.4 — content-hash the canonical descriptor on register
    # so the MCP server can snapshot the catalog atomically and the
    # agent runtime can stamp the hash set onto every run row.
    try:
        DATA_MCP_TOOL_HASHES[name] = compute_descriptor_hash(cls)
    except Exception:  # noqa: BLE001 - never block registration on a hash glitch
        logger.warning("descriptor_hash computation failed for %s", name, exc_info=True)
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


def compute_descriptor_hash(cls: type[DataMCPTool]) -> str:
    """Return the SHA-256 of the canonical-JSON form of a tool descriptor.

    Phase 5 §8.4. The "canonical-JSON form" is
    ``json.dumps(descriptor, sort_keys=True, separators=(',', ':'))``
    over the dict returned by
    :meth:`DataMCPTool.to_mcp_tool_descriptor`. Stable across Python
    versions and dict-iteration order.
    """
    descriptor = cls.to_mcp_tool_descriptor()
    canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def descriptor_hash_for(name: str) -> str | None:
    """Return the cached descriptor hash for a registered tool, or ``None``."""
    return DATA_MCP_TOOL_HASHES.get(name)


def snapshot_catalog() -> dict[str, dict[str, Any]]:
    """Phase 5 §8.4 — return the full catalog snapshot for ORM persistence.

    Each row is keyed by tool name and carries:
      - ``descriptor_hash``: SHA-256 of the canonical-JSON descriptor
      - ``descriptor_json``: the descriptor dict itself

    The MCP server persists this via
    :func:`aqp.persistence.models_mcp_tools.upsert_tool_versions` on
    boot; an unchanged hash is a no-op (`INSERT ON CONFLICT DO NOTHING`).
    """
    out: dict[str, dict[str, Any]] = {}
    for name in sorted(DATA_MCP_TOOLS):
        cls = DATA_MCP_TOOLS[name]
        descriptor = cls.to_mcp_tool_descriptor()
        out[name] = {
            "descriptor_hash": DATA_MCP_TOOL_HASHES.get(name)
            or compute_descriptor_hash(cls),
            "descriptor_json": descriptor,
        }
    return out


__all__ = [
    "DATA_MCP_TOOL_HASHES",
    "DATA_MCP_TOOLS",
    "compute_descriptor_hash",
    "descriptor_hash_for",
    "get_data_mcp_tool",
    "list_data_mcp_tools",
    "register_data_mcp_tool",
    "snapshot_catalog",
]
