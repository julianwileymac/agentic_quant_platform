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
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from aqp.config import settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    import duckdb  # noqa: F401
    import pyarrow as pa  # noqa: F401
    from pyiceberg.catalog import Catalog  # noqa: F401
    from pyiceberg.table import Table  # noqa: F401

logger = logging.getLogger(__name__)


class IcebergUnavailableError(RuntimeError):
    """Raised when the optional pyiceberg extra is missing."""


_LOCK = threading.Lock()


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
    """Invalidate the cached catalog handle (used by tests)."""
    get_catalog.cache_clear()


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
            catalog.create_namespace(ns_tuple)
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
        except Exception:  # noqa: BLE001
            logger.debug("list_tables(%s) failed", ns, exc_info=True)
    return sorted(items)


def load_table(identifier: str | tuple[str, ...]) -> "Table | None":
    catalog = get_catalog()
    ns, name = split_identifier(identifier)
    try:
        return catalog.load_table((*ns.split("."), name))
    except Exception:  # noqa: BLE001
        logger.debug("load_table(%s.%s) miss", ns, name)
        return None


def drop_table(identifier: str | tuple[str, ...]) -> bool:
    catalog = get_catalog()
    ns, name = split_identifier(identifier)
    try:
        catalog.drop_table((*ns.split("."), name))
        return True
    except Exception:  # noqa: BLE001
        logger.debug("drop_table(%s.%s) failed", ns, name, exc_info=True)
        return False


def create_or_replace_table(
    identifier: str | tuple[str, ...],
    arrow_schema: "pa.Schema",
    *,
    properties: dict[str, str] | None = None,
) -> "Table":
    """Drop ``identifier`` if present, then create a fresh table from ``arrow_schema``.

    PyIceberg's ``Catalog.create_table`` accepts a :class:`pyarrow.Schema`
    directly and assigns field ids on the way in, so we hand the Arrow
    schema through unchanged rather than pre-converting via
    ``pyarrow_to_schema`` (which only supports schemas already carrying
    Iceberg field-id metadata).
    """
    _require_pyiceberg()

    catalog = get_catalog()
    ns, name = split_identifier(identifier)
    ensure_namespace(ns)
    full_id = (*ns.split("."), name)
    drop_table(identifier)
    return catalog.create_table(
        full_id,
        schema=arrow_schema,
        properties=dict(properties or {}),
    )


def _table_exists(identifier: str | tuple[str, ...]) -> bool:
    return load_table(identifier) is not None


def append_arrow(
    identifier: str | tuple[str, ...],
    table: "pa.Table",
    *,
    create_if_missing: bool = True,
    properties: dict[str, str] | None = None,
) -> "Table":
    """Append ``table`` (pyarrow) to an Iceberg table, creating it on first call."""
    _require_pyiceberg()
    if table.num_rows == 0:
        existing = load_table(identifier)
        if existing is not None:
            return existing
        if create_if_missing:
            return create_or_replace_table(identifier, table.schema, properties=properties)
        raise ValueError(f"refused to create empty table {identifier!r} with create_if_missing=False")

    existing = load_table(identifier)
    if existing is None:
        if not create_if_missing:
            raise ValueError(f"table {identifier!r} does not exist and create_if_missing=False")
        existing = create_or_replace_table(identifier, table.schema, properties=properties)
    existing.append(table)
    return existing


def read_arrow(
    identifier: str | tuple[str, ...],
    *,
    columns: Iterable[str] | None = None,
    limit: int | None = None,
) -> "pa.Table | None":
    table = load_table(identifier)
    if table is None:
        return None
    scan = table.scan(selected_fields=tuple(columns) if columns else ("*",), limit=limit)
    try:
        return scan.to_arrow()
    except Exception:  # noqa: BLE001
        logger.debug("read_arrow(%s) failed", identifier, exc_info=True)
        return None


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
