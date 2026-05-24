"""``xform.rank`` — cross-sectional rank / z-score / bucket.

Pure-function executor over a pandas DataFrame. Reads the upstream
Arrow table from ``ctx.extras['_arrow_outputs'][upstream_node_id]``
when present (in-process compose) or materialises from the upstream
locator URI when running across processes.

Params:

- ``method`` (str, default ``"pct"``) — one of ``pct`` /
  ``z`` / ``bucket``.
- ``buckets`` (int, default 10) — only used when ``method='bucket'``.
- ``columns`` (list[str] | None) — column projection; defaults to all
  numeric columns.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def _resolve_upstream_frame(ctx: NodeContext) -> pd.DataFrame | None:
    """Pull the first upstream Arrow / DataFrame, materialising if needed."""
    arrow_outputs = ctx.extras.get("_arrow_outputs") if ctx.extras else None
    if not ctx.upstream:
        return None
    # Take the first upstream port — xform.rank is single-input.
    for port_name, locator in ctx.upstream.items():
        if not isinstance(locator, dict):
            continue
        upstream_node_id = locator.get("node_id")
        if (
            arrow_outputs
            and upstream_node_id
            and upstream_node_id in arrow_outputs
        ):
            arrow_tbl = arrow_outputs[upstream_node_id]
            try:
                return arrow_tbl.to_pandas()
            except Exception:  # noqa: BLE001
                logger.exception("upstream arrow->pandas conversion failed")
                continue
        # Out-of-process path: materialise from the URI. For Phase 0
        # we only handle the in-process compose path; the testing
        # compiler in Phase 2 plumbs MinIO URIs through here.
        uri = locator.get("uri")
        if uri:
            logger.debug(
                "xform_rank: cross-process upstream URI %s — Phase 0 stub",
                uri,
            )
    return None


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    method = str(params.get("method") or "pct").lower()
    buckets = int(params.get("buckets") or 10)
    columns = params.get("columns")

    df = _resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(
            status="error",
            error="xform.rank could not resolve upstream frame",
            log_label=f"xform_rank:{node.id}",
        )

    if columns:
        cols = [c for c in columns if c in df.columns]
    else:
        cols = list(df.select_dtypes(include=[np.number]).columns)
    if not cols:
        return NodeResult(
            status="error",
            error="xform.rank: no numeric columns to rank",
            log_label=f"xform_rank:{node.id}",
        )

    try:
        out = df.copy()
        if method == "pct":
            for c in cols:
                out[c] = out[c].rank(pct=True)
        elif method == "z":
            for c in cols:
                mu = out[c].mean()
                sd = out[c].std(ddof=0) or 1.0
                out[c] = (out[c] - mu) / sd
        elif method == "bucket":
            for c in cols:
                ranks = out[c].rank(method="first")
                bucket_ids = pd.qcut(
                    ranks, q=buckets, labels=False, duplicates="drop"
                )
                out[c] = bucket_ids
        else:
            return NodeResult(
                status="error",
                error=f"xform.rank: unknown method {method!r}",
                log_label=f"xform_rank:{node.id}",
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("xform_rank failed")
        return NodeResult(
            status="error",
            error=f"xform.rank failed: {exc}",
            log_label=f"xform_rank:{node.id}",
        )

    locator: dict[str, Any] = {
        "kind": "in_process",
        "rows": int(len(out)),
        "cols": int(out.shape[1]),
        "method": method,
        "node_id": node.id,
    }
    try:
        import pyarrow as pa

        arrow_out = pa.Table.from_pandas(out, preserve_index=False)
        ctx.extras.setdefault("_arrow_outputs", {})[node.id] = arrow_out
    except Exception:  # noqa: BLE001
        # Arrow is optional on the in-process path; downstream
        # consumers can still resolve from the locator metadata.
        logger.debug("pyarrow not installed; skipping arrow materialisation")

    return NodeResult(
        status="done",
        output_locator=locator,
        metrics={"method": method, "rows": int(len(out)), "cols": len(cols)},
        log_label=f"xform_rank:{method}",
    )


__all__ = ["execute"]
