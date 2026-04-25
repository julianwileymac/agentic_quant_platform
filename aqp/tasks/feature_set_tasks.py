"""Celery tasks for materialising feature sets at scale.

The synchronous preview path lives on the API; this task handles
multi-symbol multi-year materialisations that would block a request
thread.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="aqp.tasks.feature_set_tasks.materialize_feature_set",
)
def materialize_feature_set(
    self,
    feature_set_id: str,
    *,
    symbols: list[str],
    start: str,
    end: str,
    consumer_kind: str = "research",
    consumer_id: str | None = None,
) -> dict[str, Any]:
    """Materialise a feature set for ``symbols`` between ``start`` and ``end``.

    Writes the resulting parquet through :class:`FeatureSetService` (which
    caches under ``settings.data_dir / "feature_sets"``) and records a
    :class:`FeatureSetUsage` lineage row.
    """
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Materialising feature set {feature_set_id}")
    try:
        import pandas as pd

        from aqp.core.types import Symbol
        from aqp.data.duckdb_engine import DuckDBHistoryProvider
        from aqp.data.feature_sets import FeatureSetService

        service = FeatureSetService()
        summary = service.get(feature_set_id)
        if summary is None:
            raise ValueError(f"feature set {feature_set_id!r} not found")

        provider = DuckDBHistoryProvider()
        sym_objs = [Symbol.parse(s) for s in symbols]
        bars = provider.get_bars(sym_objs, start=pd.Timestamp(start), end=pd.Timestamp(end))
        emit(
            task_id,
            "running",
            f"Loaded {len(bars)} bars across {bars['vt_symbol'].nunique() if not bars.empty else 0} symbols",
        )

        panel = service.materialize(feature_set_id, bars)
        usage_id = service.record_usage(
            feature_set_id,
            consumer_kind=consumer_kind,
            consumer_id=consumer_id,
            meta={
                "symbols": symbols,
                "start": str(start),
                "end": str(end),
                "n_rows": int(len(panel)),
                "n_columns": int(len(panel.columns)),
            },
        )

        result = {
            "feature_set_id": feature_set_id,
            "feature_set_name": summary.name,
            "version": summary.version,
            "n_rows": int(len(panel)),
            "n_columns": int(len(panel.columns)),
            "n_symbols": int(panel["vt_symbol"].nunique()) if not panel.empty else 0,
            "usage_id": usage_id,
            "columns": [c for c in panel.columns if c not in ("timestamp", "vt_symbol")],
        }
        emit_done(task_id, result)
        return result
    except Exception as exc:  # pragma: no cover
        logger.exception("materialize_feature_set failed")
        emit_error(task_id, str(exc))
        raise
