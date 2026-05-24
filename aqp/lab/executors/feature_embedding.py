"""``feature.embedding`` — text / metadata embeddings via :func:`get_embedder`.

Wraps the existing :class:`aqp.rag.embedder.Embedder` surface so the
Lab can produce embeddings for downstream pgvector / hybrid retrieval
work (rule 11 — embeddings go through :mod:`aqp.rag.indexers/`). The
executor only computes embeddings; it does NOT write to pgvector
directly. Persistence happens through the matching ``data.vector.upsert``
MCP tool (rule 22) when the downstream node calls it.

Params:

- ``text_column`` (str, default ``"text"``) — column on the upstream
  frame to embed.
- ``id_column`` (str, optional) — column to use as the chunk id when
  the downstream node wants to persist; emitted on the output frame.
- ``model`` (str, optional) — overrides the default sentence-
  transformers model (defaults to ``settings.rag_embedder``).
- ``max_rows`` (int, default 5000) — guard against accidentally
  embedding millions of rows from an Iceberg scan.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    text_column = str(params.get("text_column") or "text")
    id_column = params.get("id_column")
    max_rows = int(params.get("max_rows") or 5000)

    df = resolve_upstream_frame(ctx)
    if df is None:
        return NodeResult(
            status="error",
            error="feature.embedding requires an upstream FRAME with a text column",
            log_label="feature.embedding:no_upstream",
        )
    if text_column not in df.columns:
        return NodeResult(
            status="error",
            error=f"feature.embedding: text_column {text_column!r} not in upstream frame",
            log_label="feature.embedding:bad_column",
        )
    if len(df) > max_rows:
        return NodeResult(
            status="error",
            error=(
                f"feature.embedding: {len(df)} rows exceeds max_rows={max_rows}. "
                "Slice upstream or raise params.max_rows."
            ),
            log_label="feature.embedding:too_many_rows",
        )

    try:
        from aqp.rag.embedder import get_embedder
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"embedder import failed: {exc}",
            log_label="feature.embedding:no_embedder",
        )

    try:
        embedder = get_embedder()
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"could not initialise embedder: {exc}",
            log_label="feature.embedding:embedder_init_fail",
        )

    texts = df[text_column].astype(str).fillna("").tolist()
    try:
        vectors = embedder.embed(texts)
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"embedder.embed failed: {exc}",
            log_label="feature.embedding:embed_fail",
        )

    arr = np.asarray(vectors, dtype=float)
    if arr.ndim != 2 or arr.shape[0] != len(df):
        return NodeResult(
            status="error",
            error=(
                f"embedder returned unexpected shape {arr.shape}; expected (n_rows, dim)"
            ),
            log_label="feature.embedding:bad_shape",
        )

    out = df.copy()
    out["_embedding"] = list(arr.tolist())
    if id_column and id_column in df.columns:
        out["_chunk_id"] = df[id_column].astype(str)
    stash_arrow_output(ctx, node.id, out)
    embedder_name = getattr(embedder, "name", embedder.__class__.__name__)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, out, kind="embedding"),
            "embedder": embedder_name,
            "dim": int(arr.shape[1]),
            "text_column": text_column,
            "id_column": id_column,
        },
        metrics={
            "rows": int(arr.shape[0]),
            "dim": int(arr.shape[1]),
        },
        log_label=f"feature.embedding:{embedder_name}",
    )


__all__ = ["execute"]
