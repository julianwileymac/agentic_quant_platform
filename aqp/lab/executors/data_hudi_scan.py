"""``data.hudi_scan`` — read a Hudi snapshot via :class:`HudiDataset`.

Wraps :mod:`aqp.data.datasets.kinds.hudi.HudiDataset` so the Lab
executor honours the Hudi namespace guard (rule 46) and never writes
through ``append_arrow``. Hudi reads require pyspark + the
hudi-spark-bundle on the classpath; when those aren't installed we
return a structured error so the user sees a clear actionable
message rather than a stack trace.

Params:

- ``namespace`` (str, required) — Hudi namespace (will be wrapped
  through ``hudi_namespace(...)`` so the ``aqp_hudi_`` prefix lands
  automatically).
- ``table`` (str, required).
- ``record_key_field`` / ``precombine_field`` — required by the
  :class:`HudiDataset` spec validator.
- ``snapshot_query`` (str, optional) — point-in-time read SQL the
  HudiDataset hands to Spark.
- ``limit`` (int, optional) — apply via pandas ``.head()`` after
  load so the locator stays bounded.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.lab.executors._helpers import base_locator, stash_arrow_output
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    namespace = str(params.get("namespace") or "").strip()
    table_name = str(params.get("table") or "").strip()
    if not namespace or not table_name:
        return NodeResult(
            status="error",
            error="data.hudi_scan requires both params.namespace and params.table",
            log_label="data.hudi_scan:missing_ids",
        )

    try:
        from aqp.data.datasets.kinds.hudi import HudiDataset
        from aqp.data.datasets.spec import DatasetSpec
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"hudi dataset surface unavailable: {exc}",
            log_label="data.hudi_scan:import_fail",
        )

    spec = DatasetSpec(
        name=f"lab-hudi-{node.id}",
        kind="hudi",
        config={
            "namespace": namespace,
            "table": table_name,
            "record_key_field": params.get("record_key_field") or "id",
            "precombine_field": params.get("precombine_field") or "ts",
            "partition_path_field": params.get("partition_path_field") or "",
            "table_type": params.get("table_type") or "MERGE_ON_READ",
            "snapshot_query": params.get("snapshot_query"),
        },
    )

    try:
        dataset = HudiDataset(spec)
        loaded = dataset._load()  # noqa: SLF001 — DatasetSpec is the public surface
    except RuntimeError as exc:
        return NodeResult(
            status="error",
            error=str(exc),
            log_label="data.hudi_scan:pyspark_unavailable",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("data.hudi_scan load failed")
        return NodeResult(
            status="error",
            error=f"hudi scan failed: {exc}",
            log_label="data.hudi_scan:load_fail",
        )

    # HudiDataset returns either a pandas DataFrame (when toPandas is
    # called inside _load) or a Spark DataFrame. Normalise to pandas
    # so downstream executors that expect a Frame can read.
    df = _coerce_to_pandas(loaded)
    if df is None:
        return NodeResult(
            status="error",
            error="hudi scan returned an unrecognised payload type",
            log_label="data.hudi_scan:bad_payload",
        )
    limit = params.get("limit")
    if isinstance(limit, int) and limit > 0:
        df = df.head(limit)
    stash_arrow_output(ctx, node.id, df)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, df, kind="hudi_scan"),
            "namespace": namespace,
            "table": table_name,
            "snapshot_query": params.get("snapshot_query"),
        },
        metrics={
            "rows": int(len(df)),
            "cols": int(df.shape[1]) if hasattr(df, "shape") else 0,
        },
        log_label=f"data.hudi_scan:{namespace}.{table_name}",
    )


def _coerce_to_pandas(payload: Any) -> Any:
    """Best-effort Spark/Arrow/pandas -> pandas conversion."""
    if payload is None:
        return None
    if hasattr(payload, "toPandas"):
        try:
            return payload.toPandas()
        except Exception:  # noqa: BLE001
            logger.debug("Spark toPandas failed", exc_info=True)
    if hasattr(payload, "to_pandas"):
        try:
            return payload.to_pandas()
        except Exception:  # noqa: BLE001
            logger.debug("arrow to_pandas failed", exc_info=True)
    # Already a pandas DataFrame (or compatible).
    if hasattr(payload, "shape") and hasattr(payload, "columns"):
        return payload
    return None


__all__ = ["execute"]
