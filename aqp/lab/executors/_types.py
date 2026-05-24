"""Per-node execution envelope + result dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeContext:
    """Per-node runtime envelope passed by the compiler.

    ``upstream`` maps input port name -> output_locator JSON of the
    upstream node (typically ``{"kind": "minio", "uri": "s3://...", "schema": {...}}``).
    The executor pulls / materialises whatever it needs via these
    locators rather than receiving pickled ORM / Arrow objects (AGENTS
    rule 5: inter-task state goes through Postgres / object storage).
    """

    run_id: str
    node_id: str
    node_type: str
    upstream: dict[str, Any] = field(default_factory=dict)
    output_root: str | None = None
    task_id: str | None = None
    request_context: Any | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeResult:
    """Per-node executor return value.

    ``output_locator`` is the pointer to whatever the executor wrote
    (Iceberg identifier, MinIO URI, in-memory JSON, ...). Downstream
    executors receive this as their ``ctx.upstream[port_name]``.
    """

    status: str = "done"
    output_locator: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    log_label: str | None = None


__all__ = ["NodeContext", "NodeResult"]
