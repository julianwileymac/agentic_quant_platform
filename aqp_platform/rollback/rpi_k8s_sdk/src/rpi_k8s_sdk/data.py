"""Data-plane access helpers (Iceberg + DuckDB) for local AQP / SDK code.

These helpers stitch together the SDK's MinIO + Iceberg primitives into the
shape AQP code expects.  When AQP itself is importable (i.e. the developer
is running ``rpi-k8s-sdk[aqp]`` inside an AQP venv), the helpers delegate
to AQP's own ``aqp.data.iceberg_catalog`` / ``aqp.data.duckdb_engine`` so
that there is exactly one code path for catalog access.

When AQP is not installed, the helpers fall back to PyIceberg + DuckDB
configured directly against the cluster MinIO endpoint.  This makes the
module usable from notebooks that just want a quick ad-hoc query without
pulling the full AQP dependency tree.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .access import LocalAccessSettings, load_settings
from .iceberg import IcebergClient

logger = logging.getLogger(__name__)


def _aqp_available() -> bool:
    try:
        import aqp.data.iceberg_catalog  # noqa: F401

        return True
    except ImportError:
        return False


def iceberg_table(
    name: str,
    *,
    namespace: str = "default",
    settings: Optional[LocalAccessSettings] = None,
) -> Any:
    """Return a PyIceberg ``Table`` handle for ``namespace.name``.

    Delegates to :func:`aqp.data.iceberg_catalog.load_table` when AQP is
    importable so AQP and SDK code share one catalog connection.  Otherwise
    falls back to the SDK's :class:`IcebergClient` which talks to the REST
    catalog configured in :class:`LocalAccessSettings`.
    """

    if _aqp_available():
        try:
            from aqp.data import iceberg_catalog  # type: ignore

            if hasattr(iceberg_catalog, "load_table"):
                return iceberg_catalog.load_table(name, namespace=namespace)
            if hasattr(iceberg_catalog, "_get_catalog"):
                catalog = iceberg_catalog._get_catalog()
                return catalog.load_table(f"{namespace}.{name}")
        except Exception:
            logger.exception("AQP iceberg_catalog delegation failed; falling back to SDK")

    client = IcebergClient(settings or load_settings())
    catalog = client.load_catalog()
    return catalog.load_table(f"{namespace}.{name}")


def duckdb_engine(
    *,
    settings: Optional[LocalAccessSettings] = None,
    s3: bool = True,
) -> Any:
    """Return a DuckDB connection pre-configured for cluster MinIO.

    When AQP is importable this returns whatever ``aqp.data.duckdb_engine``
    exposes (typically a context manager / function that yields a connection).
    Otherwise it constructs a fresh in-memory DuckDB connection with the S3
    credentials from :class:`LocalAccessSettings` already loaded so
    ``read_parquet('s3://...')`` works out of the box.
    """

    if _aqp_available():
        try:
            from aqp.data import duckdb_engine as aqp_duckdb  # type: ignore

            if callable(aqp_duckdb):
                return aqp_duckdb()
            if hasattr(aqp_duckdb, "get_engine"):
                return aqp_duckdb.get_engine()
        except Exception:
            logger.exception("AQP duckdb_engine delegation failed; falling back to SDK")

    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - optional extra
        raise RuntimeError(
            "Install rpi_k8s_sdk[aqp] (or pip install duckdb) to use duckdb_engine"
        ) from exc

    active = settings or load_settings()
    con = duckdb.connect(database=":memory:")
    if s3:
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(f"SET s3_endpoint='{active.minio_endpoint.replace('http://', '').replace('https://', '')}';")
        con.execute(f"SET s3_access_key_id='{active.minio_access_key}';")
        con.execute(f"SET s3_secret_access_key='{active.minio_secret_key}';")
        con.execute(f"SET s3_region='{active.minio_region}';")
        con.execute("SET s3_url_style='path';")
        con.execute(
            f"SET s3_use_ssl={'true' if active.minio_endpoint.startswith('https://') else 'false'};"
        )
    return con
