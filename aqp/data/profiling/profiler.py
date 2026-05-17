"""Compute Arrow-native column statistics for a dataset.

The profiler runs locally by default (PyArrow + small pandas helpers)
and falls back to Dask / Ray when ``engine="dask"`` / ``engine="ray"``
is requested. Any backend failure logs and degrades to local mode
because profiling is best-effort: returning *some* stats is better
than blocking the engine.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


def compute_profile(
    table: pa.Table,
    *,
    engine: str = "auto",
    topk: int | None = None,
    sample_rows: int | None = None,
) -> dict[str, Any]:
    """Return a JSON-friendly profile dict for ``table``.

    Shape::

        {
            "rows": int,
            "bytes": int,
            "engine": "local" | "dask" | "ray",
            "computed_at": "<iso>",
            "columns": [
                {
                    "name": str,
                    "dtype": str,
                    "nulls": int,
                    "null_fraction": float,
                    "distinct_estimate": int,
                    "min": Any | null,
                    "max": Any | null,
                    "topk": [{"value": Any, "count": int}, ...] | null,
                },
                ...
            ],
        }
    """
    from aqp.config import settings

    engine = (engine or "auto").lower()
    requested = engine
    if engine == "auto":
        engine = settings.profile_default_engine or "local"
        if engine == "auto":
            engine = "local"

    topk = topk or settings.profile_topk or 10
    sample_rows = sample_rows or settings.profile_distinct_sample_rows or 200_000

    chosen = "local"
    profile: dict[str, Any] | None = None

    if engine == "dask":
        try:
            profile = _compute_with_dask(table, topk=topk, sample_rows=sample_rows)
            chosen = "dask"
        except Exception as exc:  # noqa: BLE001
            logger.warning("dask profile failed (%s); falling back to local", exc)
    elif engine == "ray":
        try:
            profile = _compute_with_ray(table, topk=topk, sample_rows=sample_rows)
            chosen = "ray"
        except Exception as exc:  # noqa: BLE001
            logger.warning("ray profile failed (%s); falling back to local", exc)

    if profile is None:
        profile = _compute_local(table, topk=topk, sample_rows=sample_rows)
        chosen = "local"

    profile.update(
        {
            "engine": chosen,
            "requested_engine": requested,
            "computed_at": datetime.utcnow().isoformat(),
        }
    )
    return profile


def profile_iceberg_table(
    namespace: str,
    name: str,
    *,
    head_rows: int = 200_000,
    engine: str = "auto",
    topk: int | None = None,
) -> dict[str, Any]:
    """Read up to ``head_rows`` from an Iceberg table and profile it."""
    from aqp.data.iceberg_catalog import read_arrow

    identifier = f"{namespace}.{name}"
    try:
        table = read_arrow(identifier, limit=head_rows)
    except Exception as exc:  # noqa: BLE001
        logger.warning("profile_iceberg_table read failed for %s: %s", identifier, exc)
        return {
            "rows": 0,
            "bytes": 0,
            "columns": [],
            "engine": "local",
            "computed_at": datetime.utcnow().isoformat(),
            "error": str(exc),
        }
    return compute_profile(table, engine=engine, topk=topk)


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


def _compute_local(
    table: pa.Table,
    *,
    topk: int,
    sample_rows: int,
) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.compute as pc

    rows = int(table.num_rows)
    nbytes = int(table.nbytes)
    columns: list[dict[str, Any]] = []
    for field in table.schema:
        col = table.column(field.name)
        nulls = int(pc.sum(pc.is_null(col)).as_py() or 0)
        col_summary: dict[str, Any] = {
            "name": field.name,
            "dtype": str(field.type),
            "nulls": nulls,
            "null_fraction": float(nulls) / rows if rows else 0.0,
        }
        try:
            non_null = pc.drop_null(col)
            try:
                col_summary["distinct_estimate"] = int(
                    pc.count_distinct(non_null.slice(0, sample_rows)).as_py() or 0
                )
            except Exception:  # noqa: BLE001
                col_summary["distinct_estimate"] = None
            try:
                col_summary["min"] = pc.min(non_null).as_py()
                col_summary["max"] = pc.max(non_null).as_py()
            except Exception:  # noqa: BLE001
                col_summary["min"] = None
                col_summary["max"] = None
            try:
                vc = pc.value_counts(non_null.slice(0, sample_rows))
                col_summary["topk"] = _value_counts_to_topk(vc, topk)
            except Exception:  # noqa: BLE001
                col_summary["topk"] = None
        except Exception:  # noqa: BLE001
            pass
        columns.append(col_summary)

    return {
        "rows": rows,
        "bytes": nbytes,
        "columns": columns,
    }


def _value_counts_to_topk(value_counts: Any, topk: int) -> list[dict[str, Any]]:
    """Convert the result of ``pc.value_counts`` into a JSON-friendly topk."""
    out: list[dict[str, Any]] = []
    try:
        items = value_counts.to_pylist()
    except Exception:  # noqa: BLE001
        return out
    items.sort(key=lambda entry: entry.get("counts", 0), reverse=True)
    for entry in items[:topk]:
        out.append({"value": entry.get("values"), "count": int(entry.get("counts", 0))})
    return out


def _compute_with_dask(
    table: pa.Table,
    *,
    topk: int,
    sample_rows: int,
) -> dict[str, Any]:
    import dask.dataframe as dd

    df = table.to_pandas()
    ddf = dd.from_pandas(df, npartitions=max(1, len(df) // 250_000) or 1)

    rows = int(len(df))
    nbytes = int(table.nbytes)
    columns: list[dict[str, Any]] = []
    for col in df.columns:
        s = df[col]
        nulls = int(s.isna().sum())
        col_summary: dict[str, Any] = {
            "name": col,
            "dtype": str(s.dtype),
            "nulls": nulls,
            "null_fraction": float(nulls) / rows if rows else 0.0,
        }
        try:
            non_null = ddf[col].dropna()
            distinct = int(non_null.head(sample_rows).nunique())
            col_summary["distinct_estimate"] = distinct
        except Exception:  # noqa: BLE001
            col_summary["distinct_estimate"] = None
        try:
            col_summary["min"] = non_null.min().compute() if rows else None
            col_summary["max"] = non_null.max().compute() if rows else None
        except Exception:  # noqa: BLE001
            col_summary["min"] = None
            col_summary["max"] = None
        try:
            vc = non_null.value_counts().head(topk).compute()
            col_summary["topk"] = [
                {"value": idx, "count": int(cnt)} for idx, cnt in vc.items()
            ]
        except Exception:  # noqa: BLE001
            col_summary["topk"] = None
        columns.append(col_summary)
    return {"rows": rows, "bytes": nbytes, "columns": columns}


def _compute_with_ray(
    table: pa.Table,
    *,
    topk: int,
    sample_rows: int,
) -> dict[str, Any]:
    import ray
    from ray import data as ray_data

    if not ray.is_initialized():
        ray.init(ignore_reinit_error=True)

    ds = ray_data.from_arrow(table)
    df = ds.to_pandas()
    rows = int(len(df))
    nbytes = int(table.nbytes)
    columns: list[dict[str, Any]] = []
    for col in df.columns:
        s = df[col]
        nulls = int(s.isna().sum())
        col_summary: dict[str, Any] = {
            "name": col,
            "dtype": str(s.dtype),
            "nulls": nulls,
            "null_fraction": float(nulls) / rows if rows else 0.0,
        }
        try:
            non_null = s.dropna()
            col_summary["distinct_estimate"] = int(non_null.head(sample_rows).nunique())
            col_summary["min"] = non_null.min() if rows else None
            col_summary["max"] = non_null.max() if rows else None
            vc = non_null.value_counts().head(topk)
            col_summary["topk"] = [
                {"value": idx, "count": int(cnt)} for idx, cnt in vc.items()
            ]
        except Exception:  # noqa: BLE001
            col_summary["distinct_estimate"] = None
            col_summary["min"] = None
            col_summary["max"] = None
            col_summary["topk"] = None
        columns.append(col_summary)
    return {"rows": rows, "bytes": nbytes, "columns": columns}


__all__ = ["compute_profile", "profile_iceberg_table"]
