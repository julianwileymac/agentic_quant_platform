"""Shared utilities for Data Lab executors.

Phase 2-5 executors all need the same plumbing: resolve an upstream
Arrow / pandas frame, stash an output on ``ctx.extras['_arrow_outputs']``,
record a typed locator dict. Putting that in one place keeps the
per-executor file tiny (often <30 lines of real logic) and means
adding a new node is mostly a one-file change.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.lab.executors._types import NodeContext

logger = logging.getLogger(__name__)


def resolve_upstream_frame(
    ctx: NodeContext,
    *,
    prefer_port: str | None = None,
) -> pd.DataFrame | None:
    """Pull the first / preferred upstream port's frame.

    Tries (in order):

    1. ``ctx.extras["_arrow_outputs"][upstream_node_id]`` — the
       in-process compose path (Phase 0 / Phase 2 inline runs).
    2. ``ctx.upstream[port].uri`` — the MinIO Parquet locator (Phase
       2 Celery dispatch).

    Returns ``None`` when no upstream is reachable.
    """
    if not ctx.upstream:
        return None
    arrow_outputs = ctx.extras.get("_arrow_outputs") if ctx.extras else None
    port_order = (
        [prefer_port, *[p for p in ctx.upstream if p != prefer_port]]
        if prefer_port
        else list(ctx.upstream.keys())
    )
    for port in port_order:
        locator = ctx.upstream.get(port)
        if not isinstance(locator, dict):
            continue
        upstream_node_id = locator.get("node_id")
        if arrow_outputs and upstream_node_id and upstream_node_id in arrow_outputs:
            try:
                return arrow_outputs[upstream_node_id].to_pandas()
            except Exception:  # noqa: BLE001
                logger.debug("arrow->pandas failed", exc_info=True)
        uri = locator.get("uri") or locator.get("identifier")
        if uri and isinstance(uri, str) and uri.startswith("iceberg://"):
            try:
                from aqp.data import iceberg_catalog

                ident = uri.removeprefix("iceberg://")
                arrow_table = iceberg_catalog.read_arrow(ident)
                if arrow_table is not None:
                    return arrow_table.to_pandas()
            except Exception:  # noqa: BLE001
                logger.debug("iceberg materialise from upstream uri failed", exc_info=True)
        if uri and isinstance(uri, str) and uri.endswith(".parquet"):
            try:
                return pd.read_parquet(uri)
            except Exception:  # noqa: BLE001
                logger.debug("parquet read from upstream uri failed", exc_info=True)
    return None


def stash_arrow_output(ctx: NodeContext, node_id: str, df: pd.DataFrame) -> None:
    """Cache an Arrow table on ``ctx.extras`` for downstream executors."""
    try:
        import pyarrow as pa

        arrow_out = pa.Table.from_pandas(df, preserve_index=False)
        ctx.extras.setdefault("_arrow_outputs", {})[node_id] = arrow_out
    except Exception:  # noqa: BLE001
        # Arrow is optional on the in-process path. Downstream
        # executors will receive only the locator metadata in that
        # case and degrade to "no upstream frame".
        logger.debug("pyarrow not installed; skipping arrow materialisation", exc_info=True)


def base_locator(node_id: str, df: pd.DataFrame, *, kind: str = "in_process") -> dict[str, Any]:
    return {
        "kind": kind,
        "rows": int(len(df)),
        "cols": int(df.shape[1]) if hasattr(df, "shape") else 0,
        "node_id": node_id,
    }


def numeric_columns(df: pd.DataFrame, requested: list[str] | None = None) -> list[str]:
    if requested:
        return [c for c in requested if c in df.columns]
    return list(df.select_dtypes(include=[np.number]).columns)


__all__ = [
    "base_locator",
    "numeric_columns",
    "resolve_upstream_frame",
    "stash_arrow_output",
]
