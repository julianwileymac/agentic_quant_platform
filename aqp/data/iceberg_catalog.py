"""PyIceberg-backed catalog wrapper used by the generic ingestion pipeline.

Two modes are supported transparently:

- **REST catalog** (preferred for docker-compose / k8s deployments). Configure
  via ``AQP_ICEBERG_REST_URI`` together with the ``AQP_S3_*`` knobs and
  ``AQP_ICEBERG_S3_WAREHOUSE``.
- **SQL fallback** for laptop/dev usage. Uses a sqlite metadata DB inside
  ``AQP_ICEBERG_WAREHOUSE`` and the same directory as the warehouse root.

The wrapper exposes a small, opinionated surface used by the ingestion
pipeline and the FastAPI catalog routes:

- :func:`get_catalog` — cached :class:`pyiceberg.catalog.Catalog` handle.
- :func:`ensure_namespace` — idempotent namespace creation.
- :func:`create_or_replace_table` — drop+create a table with the given
  Arrow schema (used when the materializer detects a schema reset).
- :func:`append_arrow` — append a :class:`pyarrow.Table` to an existing
  Iceberg table, creating it on first call.
- :func:`list_tables` / :func:`load_table` / :func:`drop_table` — basic
  catalog plumbing.
- :func:`read_arrow` — head/scan helper that returns a :class:`pyarrow.Table`.
- :func:`iceberg_to_duckdb_view` — register the current snapshot as a
  DuckDB view by reading the underlying Parquet plan-files directly.

Failures are surfaced loudly: if the ``iceberg`` extra isn't installed we
raise a clear :class:`RuntimeError` so callers can decide whether to fall
back to the legacy parquet path.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from aqp.config import settings
from aqp.observability import get_tracer

if TYPE_CHECKING:  # pragma: no cover - typing only
    import duckdb  # noqa: F401
    import pyarrow as pa  # noqa: F401
    from pyiceberg.catalog import Catalog  # noqa: F401
    from pyiceberg.table import Table  # noqa: F401

logger = logging.getLogger(__name__)
_tracer = get_tracer("aqp.data.iceberg_catalog")


class IcebergUnavailableError(RuntimeError):
    """Raised when the optional pyiceberg extra is missing or the catalog is unreachable."""


class IcebergTableNotFoundError(IcebergUnavailableError):
    """Raised when a table identifier is not present in the catalog."""


_LOCK = threading.Lock()


_TABLE_NOT_FOUND_MARKERS = (
    "no such table",
    "nosuchtable",
    "tablenotfound",
    "table_not_found",
)

_SQLITE_LOCK_MARKERS = (
    "database is locked",
    "database table is locked",
    "sqlite_busy",
)


def _is_table_not_found(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if any(marker in msg for marker in _TABLE_NOT_FOUND_MARKERS):
        return True
    return type(exc).__name__ in {"NoSuchTableError", "TableNotFoundError"}


def _is_sqlite_locked(exc: BaseException) -> bool:
    msg = str(exc).lower()
    if any(marker in msg for marker in _SQLITE_LOCK_MARKERS):
        return True
    return type(exc).__name__ in {"OperationalError"} and "locked" in msg


def _retry_on_sqlite_lock(
    func: Callable[[], Any],
    *,
    attempts: int = 5,
    base_delay: float = 0.25,
    label: str = "operation",
) -> Any:
    """Retry an operation that may hit a transient SQLite ``database is locked`` error."""
    delay = float(base_delay)
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:
            if attempt >= attempts or not _is_sqlite_locked(exc):
                raise
            logger.warning(
                "Iceberg sqlite catalog locked during %s (attempt %d/%d); retrying in %.2fs",
                label,
                attempt,
                attempts,
                delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, 4.0)


def _require_pyiceberg() -> None:
    try:
        import pyiceberg  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised in CI without extra
        raise IcebergUnavailableError(
            "pyiceberg is not installed. Install with `pip install agentic-quant-platform[iceberg]` "
            "to enable the Iceberg-first data catalog."
        ) from exc


def _build_properties() -> dict[str, str]:
    """Translate AQP settings into a PyIceberg ``Catalog`` properties dict."""
    rest_uri = (settings.iceberg_rest_uri or "").strip()
    warehouse_path = Path(settings.iceberg_warehouse).expanduser().resolve()
    warehouse_path.mkdir(parents=True, exist_ok=True)

    if rest_uri:
        warehouse = (settings.iceberg_s3_warehouse or "").strip() or f"file://{warehouse_path}"
        props: dict[str, str] = {
            "type": "rest",
            "uri": rest_uri,
            "warehouse": warehouse,
        }
    else:
        sqlite_path = warehouse_path / "catalog.db"
        props = {
            "type": "sql",
            "uri": f"sqlite:///{sqlite_path}",
            "warehouse": f"file://{warehouse_path}",
            "init_catalog_tables": "true",
        }

    if settings.s3_endpoint_url:
        props["s3.endpoint"] = settings.s3_endpoint_url
    if settings.s3_access_key:
        props["s3.access-key-id"] = settings.s3_access_key
    if settings.s3_secret_key:
        props["s3.secret-access-key"] = settings.s3_secret_key
    if settings.s3_region:
        props["s3.region"] = settings.s3_region
    if settings.s3_path_style_access:
        props["s3.path-style-access"] = "true"
    return props


@lru_cache(maxsize=1)
def get_catalog() -> "Catalog":
    """Return a cached :class:`pyiceberg.catalog.Catalog` handle."""
    _require_pyiceberg()
    from pyiceberg.catalog import load_catalog

    props = _build_properties()
    name = settings.iceberg_catalog_name or "aqp"
    logger.debug("Loading Iceberg catalog %s with type=%s", name, props.get("type"))
    return load_catalog(name, **props)


def reset_catalog_cache() -> None:
    """Invalidate the cached catalog handle (used by tests).

    Defensive against monkeypatching: if ``get_catalog`` has been replaced
    with a plain function (e.g. via :class:`pytest.MonkeyPatch`), it will
    not have an ``lru_cache`` ``cache_clear`` attribute. Skipping silently
    is correct because the patched function has no cache to clear.
    """
    cache_clear = getattr(get_catalog, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()


def split_identifier(identifier: str | tuple[str, ...]) -> tuple[str, str]:
    """Normalize ``"ns.table"`` or ``("ns", "table")`` to a 2-tuple."""
    if isinstance(identifier, str):
        if "." not in identifier:
            ns = settings.iceberg_namespace_default or "aqp"
            return ns, identifier
        ns, _, name = identifier.rpartition(".")
        return ns, name
    if isinstance(identifier, tuple) and len(identifier) >= 2:
        return str(identifier[-2]), str(identifier[-1])
    raise ValueError(f"unrecognised iceberg identifier: {identifier!r}")


def ensure_namespace(namespace: str) -> None:
    """Create ``namespace`` if it doesn't already exist (idempotent)."""
    catalog = get_catalog()
    ns_tuple = tuple(namespace.split("."))
    with _LOCK:
        try:
            _retry_on_sqlite_lock(
                lambda: catalog.create_namespace(ns_tuple),
                label=f"create_namespace({namespace!r})",
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "already exists" in msg or "alreadyexists" in msg or "namespacealreadyexists" in msg:
                return
            try:
                catalog.load_namespace_properties(ns_tuple)
                return
            except Exception:  # pragma: no cover
                logger.warning("create_namespace(%s) failed: %s", namespace, exc)
                raise


def list_namespaces() -> list[str]:
    catalog = get_catalog()
    out: list[str] = []
    for ns in catalog.list_namespaces():
        out.append(".".join(ns) if isinstance(ns, (tuple, list)) else str(ns))
    return sorted(out)


def list_tables(namespace: str | None = None) -> list[str]:
    catalog = get_catalog()
    items: list[str] = []
    namespaces: list[str]
    if namespace:
        namespaces = [namespace]
    else:
        namespaces = list_namespaces()
    for ns in namespaces:
        ns_tuple = tuple(ns.split("."))
        try:
            for ident in catalog.list_tables(ns_tuple):
                if isinstance(ident, (tuple, list)):
                    items.append(".".join(str(p) for p in ident))
                else:
                    items.append(str(ident))
        except Exception as exc:  # noqa: BLE001
            if _is_table_not_found(exc):
                continue
            logger.warning("list_tables(%s) failed: %s", ns, exc)
    return sorted(items)


def load_table(identifier: str | tuple[str, ...]) -> "Table | None":
    """Return the loaded Iceberg table or ``None`` if the table does not exist.

    Real catalog failures (sqlite locked, REST timeouts, missing
    pyiceberg-core, etc.) propagate as exceptions instead of being silently
    swallowed — callers that previously relied on ``None`` for "anything went
    wrong" must now distinguish "not found" from "engine error".
    """
    catalog = get_catalog()
    ns, name = split_identifier(identifier)
    try:
        return catalog.load_table((*ns.split("."), name))
    except Exception as exc:
        if _is_table_not_found(exc):
            logger.debug("load_table(%s.%s) miss", ns, name)
            return None
        raise


def drop_table(identifier: str | tuple[str, ...]) -> bool:
    catalog = get_catalog()
    ns, name = split_identifier(identifier)
    try:
        _retry_on_sqlite_lock(
            lambda: catalog.drop_table((*ns.split("."), name)),
            label=f"drop_table({identifier!r})",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        if _is_table_not_found(exc):
            return False
        logger.warning("drop_table(%s.%s) failed: %s", ns, name, exc)
        return False


def _iceberg_schema_from_arrow(arrow_schema: "pa.Schema") -> "Any":
    """Convert a PyArrow schema to an Iceberg :class:`Schema` with stable field ids.

    PyIceberg 0.11+ rejects ``pyarrow_to_schema(..., name_mapping=None)`` for
    Arrow schemas without embedded Parquet field ids (the error about
    ``schema.name-mapping.default``). The catalog uses the same path as
    ``Catalog._convert_schema_if_needed`` plus ``assign_fresh_schema_ids`` for
    new tables.
    """
    from pyiceberg.catalog import Catalog
    from pyiceberg.schema import assign_fresh_schema_ids

    proto = Catalog._convert_schema_if_needed(arrow_schema)
    return assign_fresh_schema_ids(proto)


def create_or_replace_table(
    identifier: str | tuple[str, ...],
    arrow_schema: "pa.Schema",
    *,
    properties: dict[str, str] | None = None,
    partition_spec: "Any" = None,
) -> "Table":
    """Drop ``identifier`` if present, then create a fresh table from ``arrow_schema``.

    PyIceberg's ``Catalog.create_table`` accepts either a :class:`pyarrow.Schema`
    or an Iceberg :class:`~pyiceberg.schema.Schema`. For **unpartitioned** tables
    we pass Arrow through unchanged. For **dict-based** partition specs we pass a
    pre-assigned Iceberg schema so partition ``source_id`` values match what
    ``new_table_metadata`` expects (see :func:`_resolve_partition_spec`).

    ``partition_spec`` may be either:
    - a :class:`pyiceberg.partitioning.PartitionSpec` instance (used as-is); or
    - a list/tuple of partition descriptor dicts of the form
      ``{"source_column": str, "transform": str, "name": str}``, in which case
      it is compiled into a :class:`PartitionSpec` against the given Arrow
      schema. Supported transforms: ``identity``, ``year``, ``month``,
      ``day``, ``hour``, ``bucket[N]``, ``truncate[N]``.
    """
    _require_pyiceberg()

    catalog = get_catalog()
    ns, name = split_identifier(identifier)
    ensure_namespace(ns)
    full_id = (*ns.split("."), name)
    drop_table(identifier)

    spec = _resolve_partition_spec(partition_spec, arrow_schema)
    partitioned_from_dicts = isinstance(partition_spec, (list, tuple)) and len(partition_spec) > 0
    schema_for_create: Any = arrow_schema
    if partitioned_from_dicts:
        schema_for_create = _iceberg_schema_from_arrow(arrow_schema)

    create_kwargs: dict[str, Any] = {
        "schema": schema_for_create,
        "properties": dict(properties or {}),
    }
    if spec is not None:
        create_kwargs["partition_spec"] = spec
    return _retry_on_sqlite_lock(
        lambda: catalog.create_table(full_id, **create_kwargs),
        label=f"create_table({identifier!r})",
    )


def _resolve_partition_spec(spec: "Any", arrow_schema: "pa.Schema") -> "Any":
    """Coerce a list-of-dicts partition descriptor into a PyIceberg PartitionSpec.

    Returns ``None`` for ``spec is None`` or the unchanged spec when it
    already looks like a PyIceberg ``PartitionSpec``. Errors raise
    :class:`ValueError` so callers can surface configuration mistakes.
    """
    if spec is None:
        return None
    try:
        from pyiceberg.partitioning import PartitionField, PartitionSpec
        from pyiceberg.transforms import (
            BucketTransform,
            DayTransform,
            HourTransform,
            IdentityTransform,
            MonthTransform,
            TruncateTransform,
            YearTransform,
        )
    except ImportError:  # pragma: no cover - exercised when iceberg extra is missing
        return None

    if isinstance(spec, PartitionSpec):
        return spec
    if not isinstance(spec, (list, tuple)):
        raise ValueError(f"unsupported partition_spec value: {type(spec).__name__}")
    if len(spec) == 0:
        return None

    # PyIceberg 0.11+: pyarrow_to_schema(..., name_mapping=None) raises for plain
    # Arrow schemas. Use the same id assignment path as Catalog.create_table.
    iceberg_schema = _iceberg_schema_from_arrow(arrow_schema)

    fields: list[PartitionField] = []
    for idx, descriptor in enumerate(spec, start=1000):
        if isinstance(descriptor, dict):
            source_column = str(descriptor.get("source_column") or descriptor.get("column") or "")
            transform_raw = str(descriptor.get("transform") or "identity").strip().lower()
            field_name = str(
                descriptor.get("name")
                or f"{source_column}_{transform_raw.split('[')[0]}"
            )
        else:
            source_column = str(getattr(descriptor, "source_column", ""))
            transform_raw = str(getattr(descriptor, "transform", "identity")).strip().lower()
            field_name = str(
                getattr(descriptor, "name", None)
                or f"{source_column}_{transform_raw.split('[')[0]}"
            )
        if not source_column:
            raise ValueError(f"partition descriptor missing source_column: {descriptor!r}")
        try:
            source_id = iceberg_schema.find_field(source_column).field_id
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"partition source column {source_column!r} not found in schema"
            ) from exc
        transform: Any
        if transform_raw == "identity":
            transform = IdentityTransform()
        elif transform_raw == "year":
            transform = YearTransform()
        elif transform_raw == "month":
            transform = MonthTransform()
        elif transform_raw == "day":
            transform = DayTransform()
        elif transform_raw == "hour":
            transform = HourTransform()
        elif transform_raw.startswith("bucket"):
            n = _parse_transform_arg(transform_raw, "bucket")
            transform = BucketTransform(num_buckets=n)
        elif transform_raw.startswith("truncate"):
            n = _parse_transform_arg(transform_raw, "truncate")
            transform = TruncateTransform(width=n)
        else:
            raise ValueError(f"unsupported partition transform: {transform_raw!r}")
        fields.append(
            PartitionField(
                source_id=source_id,
                field_id=idx,
                transform=transform,
                name=field_name,
            )
        )
    return PartitionSpec(*fields)


def _parse_transform_arg(transform_raw: str, prefix: str) -> int:
    body = transform_raw.removeprefix(prefix).strip()
    if body.startswith("[") and body.endswith("]"):
        body = body[1:-1]
    try:
        return int(body)
    except ValueError as exc:
        raise ValueError(f"invalid {prefix} transform: {transform_raw!r}") from exc


def _table_exists(identifier: str | tuple[str, ...]) -> bool:
    return load_table(identifier) is not None


def append_arrow(
    identifier: str | tuple[str, ...],
    table: "pa.Table",
    *,
    create_if_missing: bool = True,
    properties: dict[str, str] | None = None,
    partition_spec: "Any" = None,
) -> "Table":
    """Append ``table`` (pyarrow) to an Iceberg table, creating it on first call.

    ``partition_spec`` is forwarded to :func:`create_or_replace_table` when
    the table is created on first append; existing tables ignore it (Iceberg
    schema/partition evolution lives outside this helper).

    The whole operation is wrapped in an OpenTelemetry span so Jaeger shows
    every Iceberg write attached to the calling pipeline.
    """
    table_id = identifier if isinstance(identifier, str) else ".".join(identifier)
    with _tracer.start_as_current_span("iceberg.append_arrow") as span:
        try:
            span.set_attribute("iceberg.table", table_id)
            span.set_attribute("iceberg.row_count", int(table.num_rows))
            span.set_attribute("iceberg.create_if_missing", create_if_missing)
        except Exception:  # noqa: BLE001
            pass

        _require_pyiceberg()
        if table.num_rows == 0:
            existing = load_table(identifier)
            if existing is not None:
                return existing
            if create_if_missing:
                return create_or_replace_table(
                    identifier,
                    table.schema,
                    properties=properties,
                    partition_spec=partition_spec,
                )
            raise ValueError(
                f"refused to create empty table {identifier!r} with create_if_missing=False"
            )

        existing = load_table(identifier)
        if existing is None:
            if not create_if_missing:
                raise ValueError(
                    f"table {identifier!r} does not exist and create_if_missing=False"
                )
            existing = create_or_replace_table(
                identifier,
                table.schema,
                properties=properties,
                partition_spec=partition_spec,
            )
        _retry_on_sqlite_lock(
            lambda: existing.append(table),
            label=f"append_arrow({table_id!r})",
        )
        return existing


def read_arrow(
    identifier: str | tuple[str, ...],
    *,
    columns: Iterable[str] | None = None,
    limit: int | None = None,
    row_filter: Any = None,
) -> "pa.Table | None":
    """Scan an Iceberg table and return a PyArrow table.

    Returns ``None`` only when the table does not exist. Other failures
    (sqlite lock, S3 timeout, missing pyiceberg-core, etc.) propagate to the
    caller — silent ``None`` returns made it impossible to tell "no data" from
    "catalog is broken".
    """
    table = load_table(identifier)
    if table is None:
        return None
    scan_kwargs: dict[str, Any] = {
        "selected_fields": tuple(columns) if columns else ("*",),
    }
    if limit is not None:
        scan_kwargs["limit"] = int(limit)
    if row_filter is not None:
        scan_kwargs["row_filter"] = row_filter
    scan = table.scan(**scan_kwargs)
    return scan.to_arrow()


def read_polars(
    identifier: str | tuple[str, ...],
    *,
    columns: Iterable[str] | None = None,
    limit: int | None = None,
    row_filter: Any = None,
):
    """Scan an Iceberg table and return a :class:`polars.DataFrame`.

    This is the canonical Polars entry point used by the event-driven
    backtester and ``_MLBaseAlpha`` feature pipeline. Built on top of
    :func:`read_arrow` so the underlying Arrow buffers are shared (Polars
    constructs zero-copy views over Arrow chunked arrays whenever the
    column dtype maps cleanly).

    Returns ``None`` only when the table does not exist; matches the
    ``read_arrow`` contract so callers can switch between the two without
    branching on missing data semantics.
    """
    arrow = read_arrow(
        identifier,
        columns=columns,
        limit=limit,
        row_filter=row_filter,
    )
    if arrow is None:
        return None
    import polars as pl  # local import keeps the heavy dep optional at module load

    return pl.from_arrow(arrow)


def health_check(*, timeout: float | None = None) -> dict[str, Any]:
    """Probe the catalog with a bounded read-only operation.

    Returns a status dict with ``ok``, ``type``, ``uri``, ``warehouse``,
    ``namespace_count``, ``elapsed_seconds``, and ``error`` keys. Never
    raises — callers can use the returned dict to decide whether to proceed.
    """
    timeout_value = (
        float(timeout)
        if timeout is not None
        else float(getattr(settings, "iceberg_health_check_timeout_seconds", 5.0) or 0.0)
    )
    deadline = (time.monotonic() + timeout_value) if timeout_value > 0 else None
    started = time.monotonic()
    info: dict[str, Any] = {
        "ok": False,
        "type": "unknown",
        "uri": "",
        "warehouse": "",
        "namespace_count": 0,
        "table_count": None,
        "elapsed_seconds": 0.0,
        "error": None,
    }
    try:
        props = _build_properties()
        info["type"] = str(props.get("type", "unknown"))
        info["uri"] = str(props.get("uri", ""))
        info["warehouse"] = str(props.get("warehouse", ""))
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"properties: {type(exc).__name__}: {exc}"
        info["elapsed_seconds"] = time.monotonic() - started
        return info

    try:
        catalog = get_catalog()
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("catalog load exceeded health-check deadline")
        namespaces = list(catalog.list_namespaces())
        info["namespace_count"] = len(namespaces)
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError("list_namespaces exceeded health-check deadline")
        info["ok"] = True
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"
    info["elapsed_seconds"] = round(time.monotonic() - started, 4)
    return info


def _build_in_expression(column: str, values: Iterable[str]) -> Any:
    """Build a PyIceberg ``In`` predicate or fall back to a string filter."""
    items = list({str(v) for v in values if v is not None and str(v) != ""})
    if not items:
        raise ValueError("cannot build In expression with no values")
    try:
        from pyiceberg.expressions import In  # type: ignore[import-not-found]

        return In(column, items)
    except Exception:  # pragma: no cover - exercised when pyiceberg API differs
        quoted = ",".join("'" + value.replace("'", "''") + "'" for value in items)
        return f"{column} IN ({quoted})"


def latest_timestamps_for_symbols(
    identifier: str | tuple[str, ...],
    symbols: Iterable[str],
    *,
    group_col: str = "vt_symbol",
    time_col: str = "timestamp",
) -> dict[str, datetime]:
    """Return ``{vt_symbol: max(time_col)}`` using a predicate-pushdown scan.

    The Iceberg row filter prunes data files by partition (typically
    ``bucket(vt_symbol)``) so the scan is bounded by the size of the
    requested symbol slice — not the entire table. Returns ``{}`` when the
    table is missing or no rows match.
    """
    sym_list = sorted({str(s) for s in symbols if s})
    if not sym_list:
        return {}
    table = load_table(identifier)
    if table is None:
        return {}
    expr = _build_in_expression(group_col, sym_list)
    arrow = table.scan(
        row_filter=expr,
        selected_fields=(group_col, time_col),
    ).to_arrow()
    if arrow is None or arrow.num_rows == 0:
        return {}

    # Arrow-native group-by + max — keeps the data in columnar Arrow
    # buffers and avoids the round-trip through Pandas. Falls back to
    # Polars only if the time column carries an unusual dtype.
    import pyarrow.compute as pc

    try:
        grouped = arrow.group_by(group_col).aggregate([(time_col, "max")])
    except Exception:
        # Polars fallback handles odd dtypes (e.g. string timestamps).
        import polars as pl

        df = pl.from_arrow(arrow).with_columns(
            pl.col(time_col).cast(pl.Datetime, strict=False)
        )
        df = df.drop_nulls(subset=[time_col])
        if df.height == 0:
            return {}
        agg = df.group_by(group_col).agg(pl.col(time_col).max())
        return {str(row[group_col]): row[time_col] for row in agg.iter_rows(named=True)}

    if grouped.num_rows == 0:
        return {}
    keys = grouped.column(group_col).to_pylist()
    times_col = grouped.column(f"{time_col}_max")
    # Drop nulls without dragging in pandas/polars.
    times_py = times_col.to_pylist()
    out: dict[str, datetime] = {}
    for key, ts in zip(keys, times_py, strict=False):
        if ts is None:
            continue
        # PyArrow returns ``datetime`` objects for timestamp arrays.
        out[str(key)] = ts
    return out


def existing_keys_for_window(
    identifier: str | tuple[str, ...],
    symbols: Iterable[str],
    time_min: Any,
    time_max: Any,
    *,
    group_col: str = "vt_symbol",
    time_col: str = "timestamp",
) -> set[tuple[str, Any]]:
    """Return the set of ``(group_col, time_col)`` keys already in the table.

    Filters by ``In(group_col, symbols)`` via Iceberg push-down, then bounds
    the result to ``[time_min, time_max]`` client-side. Designed for batch
    de-duplication so callers can drop already-loaded rows without scanning
    the whole table.
    """
    sym_list = sorted({str(s) for s in symbols if s})
    if not sym_list or time_min is None or time_max is None:
        return set()
    table = load_table(identifier)
    if table is None:
        return set()
    expr = _build_in_expression(group_col, sym_list)
    arrow = table.scan(
        row_filter=expr,
        selected_fields=(group_col, time_col),
    ).to_arrow()
    if arrow is None or arrow.num_rows == 0:
        return set()

    # Polars-native window filter — single linear scan, no Pandas DataFrame
    # construction. Polars accepts heterogenous time inputs (str, np.datetime64,
    # python datetime) so the upstream callers don't need to pre-coerce.
    import polars as pl

    df = pl.from_arrow(arrow)
    if df.height == 0:
        return set()
    if df.schema[time_col] != pl.Datetime:
        df = df.with_columns(pl.col(time_col).cast(pl.Datetime, strict=False))
    df = df.drop_nulls(subset=[time_col])
    if df.height == 0:
        return set()
    try:
        lower = pl.lit(time_min).cast(pl.Datetime)
        upper = pl.lit(time_max).cast(pl.Datetime)
    except Exception:
        # Pandas Timestamps or strings — let pandas coerce, then Polars consume.
        import pandas as pd

        lower_ts = pd.to_datetime(time_min, errors="coerce")
        upper_ts = pd.to_datetime(time_max, errors="coerce")
        if pd.isna(lower_ts) or pd.isna(upper_ts):
            return set()
        lower = pl.lit(lower_ts.to_pydatetime()).cast(pl.Datetime)
        upper = pl.lit(upper_ts.to_pydatetime()).cast(pl.Datetime)
    df = df.filter((pl.col(time_col) >= lower) & (pl.col(time_col) <= upper))
    if df.height == 0:
        return set()
    return {
        (str(row[group_col]), row[time_col])
        for row in df.select([group_col, time_col]).iter_rows(named=True)
    }


def iceberg_to_duckdb_view(
    conn: "duckdb.DuckDBPyConnection",
    identifier: str | tuple[str, ...],
    *,
    view_name: str | None = None,
) -> str | None:
    """Register the current Iceberg snapshot as a DuckDB view via ``read_parquet``.

    Returns the registered view name on success, or ``None`` if the table
    doesn't exist or has no data files. We deliberately read the plan
    files directly rather than going through the (still experimental)
    ``iceberg`` DuckDB extension so this works on stock DuckDB builds.
    """
    table = load_table(identifier)
    if table is None:
        return None
    try:
        scan = table.scan()
        files = [task.file.file_path for task in scan.plan_files()]
    except Exception:  # noqa: BLE001
        logger.debug("iceberg_to_duckdb_view plan_files miss", exc_info=True)
        return None
    if not files:
        return None

    ns, name = split_identifier(identifier)
    safe = (view_name or f"{ns}__{name}").replace(".", "__").replace("-", "_")
    _configure_duckdb_s3(conn)
    array_lit = ", ".join(_sql_string(p) for p in files)
    conn.execute(
        f"CREATE OR REPLACE VIEW {safe} AS "
        f"SELECT * FROM read_parquet([{array_lit}], union_by_name=true)"
    )
    return safe


def _sql_string(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _configure_duckdb_s3(conn: "duckdb.DuckDBPyConnection") -> None:
    """Teach DuckDB how to read Iceberg data files from MinIO/S3."""
    if not settings.s3_endpoint_url:
        return

    try:
        conn.execute("LOAD httpfs")
    except Exception:  # noqa: BLE001
        conn.execute("INSTALL httpfs")
        conn.execute("LOAD httpfs")

    parsed = urlparse(settings.s3_endpoint_url)
    endpoint = parsed.netloc or parsed.path
    use_ssl = "true" if (parsed.scheme or "http").lower() == "https" else "false"
    conn.execute(f"SET s3_endpoint={_sql_string(endpoint)}")
    conn.execute(f"SET s3_region={_sql_string(settings.s3_region or 'us-east-1')}")
    conn.execute(f"SET s3_access_key_id={_sql_string(settings.s3_access_key)}")
    conn.execute(f"SET s3_secret_access_key={_sql_string(settings.s3_secret_key)}")
    conn.execute(f"SET s3_use_ssl={use_ssl}")
    if settings.s3_path_style_access:
        conn.execute("SET s3_url_style='path'")


def snapshot_history(identifier: str | tuple[str, ...]) -> list[dict[str, Any]]:
    """Return a JSON-friendly snapshot history list (most recent last)."""
    table = load_table(identifier)
    if table is None:
        return []
    out: list[dict[str, Any]] = []
    for snap in table.snapshots():
        raw_summary = snap.summary
        if raw_summary is None:
            summary: dict[str, Any] = {}
        elif hasattr(raw_summary, "model_dump"):
            summary = dict(raw_summary.model_dump())
        elif hasattr(raw_summary, "dict"):
            summary = dict(raw_summary.dict())
        elif hasattr(raw_summary, "items"):
            summary = dict(raw_summary.items())
        else:
            summary = {}
        out.append(
            {
                "snapshot_id": int(snap.snapshot_id),
                "parent_snapshot_id": (
                    int(snap.parent_snapshot_id) if snap.parent_snapshot_id is not None else None
                ),
                "operation": str(snap.operation) if getattr(snap, "operation", None) else None,
                "timestamp_ms": int(snap.timestamp_ms),
                "summary": {k: str(v) for k, v in summary.items()},
            }
        )
    return out


def table_metadata(identifier: str | tuple[str, ...]) -> dict[str, Any]:
    """Compact metadata dict suitable for the API."""
    table = load_table(identifier)
    if table is None:
        return {}
    schema = table.schema()
    fields = [
        {
            "id": int(f.field_id),
            "name": f.name,
            "type": str(f.field_type),
            "required": bool(f.required),
            "doc": f.doc,
        }
        for f in schema.fields
    ]
    spec = table.spec()
    partitions = [
        {
            "name": p.name,
            "source_id": int(p.source_id),
            "transform": str(p.transform),
        }
        for p in spec.fields
    ] if spec else []

    snap = table.current_snapshot()
    snapshot_id = int(snap.snapshot_id) if snap else None
    location = getattr(table, "location", lambda: None)() or ""
    return {
        "fields": fields,
        "partition_spec": partitions,
        "current_snapshot_id": snapshot_id,
        "location": str(location),
        "properties": {k: str(v) for k, v in (table.properties or {}).items()},
    }
