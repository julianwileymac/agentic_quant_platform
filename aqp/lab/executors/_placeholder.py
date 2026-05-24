"""Structured placeholder executor for the 32 node types not yet wired.

Returns ``status='error'`` with a clear ``not_implemented`` reason so
the frontend status pill flips to red and the run history drawer
shows a helpful message — but the pipeline / compiler / WS contract
is still exercised end-to-end.
"""
from __future__ import annotations

from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    return NodeResult(
        status="error",
        error=(
            f"Node type {node.type!r} is registered but the Phase 0 "
            "executor is a placeholder. Implementation lands in Phase 2-5."
        ),
        log_label=f"placeholder:{node.type}",
    )


__all__ = ["execute"]
