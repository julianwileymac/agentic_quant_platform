"""Celery tasks for the multi-tenant upload + merge data plane.

Two tasks land here:

- :func:`materialise_uploaded_dataset` — turns a staged file (under
  MinIO/S3 or the local-fs fallback) into an Iceberg bronze table
  scoped to the uploader's workspace.
- :func:`merge_uploaded_datasets` — runs a relational join between
  two workspace-owned bronze tables and writes the result back as a
  new bronze (well, "silver" by intent — the join produces derived
  data) table.

Both tasks re-bind the request context so every chokepoint downstream
sees the uploader's workspace / project / user, even though Celery
runs in a separate process. The progress bus already emits
``stage`` / ``message`` frames the frontend subscribes to.
"""
from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aqp.auth.context import RequestContext
from aqp.auth.contextvars import use_context
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _build_context(
    *,
    user_id: str | None,
    workspace_id: str | None,
    project_id: str | None,
    run_id: str | None = None,
) -> RequestContext:
    """Reconstruct a :class:`RequestContext` inside the Celery worker."""
    return RequestContext(
        user_id=user_id or "",
        workspace_id=workspace_id,
        project_id=project_id,
        run_id=run_id,
    )


@contextmanager
def _local_path_for(uri: str):
    """Yield a local filesystem path for the staged URI.

    - ``file://`` URIs are used as-is.
    - ``s3://`` URIs are downloaded to a NamedTemporaryFile under the
      OS temp dir; the file is removed on exit.
    """
    parsed = urlparse(uri)
    if parsed.scheme in ("file", ""):
        yield Path(parsed.path or uri.removeprefix("file://"))
        return
    if parsed.scheme not in ("s3",):
        raise ValueError(f"unsupported staged URI scheme: {parsed.scheme!r}")

    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    suffix = Path(key).suffix or ""
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="aqp_upload_")
    os.close(fd)
    tmp = Path(tmp_path)
    try:
        from aqp.config import settings

        try:
            import boto3
            from botocore.client import Config
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "boto3 is required to download staged uploads from S3/MinIO"
            ) from exc

        client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint_url or settings.s3_endpoint_url,
            aws_access_key_id=settings.minio_access_key or settings.s3_access_key,
            aws_secret_access_key=settings.minio_secret_key or settings.s3_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        client.download_file(bucket, key, str(tmp))
        yield tmp
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            logger.debug("could not delete tmp upload %s", tmp, exc_info=True)


@celery_app.task(
    bind=True,
    name="aqp.tasks.dataset_upload_tasks.materialise_uploaded_dataset",
    autoretry_for=(),
    max_retries=0,
)
def materialise_uploaded_dataset(
    self,
    *,
    staged_uri: str,
    workspace_id: str | None,
    project_id: str | None,
    user_id: str | None,
    namespace: str,
    table_name: str,
    content_type: str | None,
    dataset_id: str,
) -> dict[str, Any]:
    """Materialise a staged upload into an Iceberg bronze table.

    Uses the existing :class:`aqp.data.pipelines.IngestionPipeline` so
    upload-driven and Director-driven ingestion share a single
    materialise path.
    """
    task_id = self.request.id or "materialise_upload"
    emit(task_id, "received", f"Materialising {table_name!r} into {namespace!r}")
    ctx = _build_context(
        user_id=user_id,
        workspace_id=workspace_id,
        project_id=project_id,
        run_id=task_id,
    )
    try:
        with _local_path_for(staged_uri) as local_path:
            emit(task_id, "staged", f"Local path: {local_path}", bytes=local_path.stat().st_size if local_path.exists() else 0)
            with use_context(ctx):
                from aqp.data.pipelines.runner import IngestionPipeline

                pipeline = IngestionPipeline()
                report = pipeline.run_path(
                    str(local_path),
                    target_namespace=namespace,
                    target_table=table_name,
                )

        result_payload: dict[str, Any] = {
            "ok": True,
            "namespace": namespace,
            "table_name": table_name,
            "dataset_id": dataset_id,
            "iceberg_identifier": f"{namespace}.{table_name}",
            "rows_written": int(getattr(report, "rows_written", 0) or 0),
            "files_consumed": int(getattr(report, "files_consumed", 0) or 0),
            "files_skipped": int(getattr(report, "files_skipped", 0) or 0),
            "truncated": bool(getattr(report, "truncated", False)),
        }
        _mark_dataset_status(
            iceberg_identifier=result_payload["iceberg_identifier"],
            workspace_id=workspace_id,
            status="ready",
            extras={"rows_written": result_payload["rows_written"]},
        )
        emit_done(task_id, result_payload)
        return result_payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("materialise_uploaded_dataset failed for %s.%s", namespace, table_name)
        _mark_dataset_status(
            iceberg_identifier=f"{namespace}.{table_name}",
            workspace_id=workspace_id,
            status="failed",
            extras={"error": str(exc)},
        )
        emit_error(task_id, str(exc))
        raise


@celery_app.task(
    bind=True,
    name="aqp.tasks.dataset_upload_tasks.merge_uploaded_datasets",
)
def merge_uploaded_datasets(
    self,
    *,
    left_identifier: str,
    right_identifier: str,
    on: list[str],
    how: str,
    target_table: str,
    workspace_id: str | None,
    project_id: str | None,
    user_id: str | None,
) -> dict[str, Any]:
    """Compute a relational join between two workspace bronze tables.

    Reads both inputs through DuckDB (so Iceberg metadata + Parquet
    files are read efficiently), performs the join in-process, and
    writes the result into ``aqp_silver_user_uploads_<ws>.{target_table}``
    via the same :func:`iceberg_catalog.append_arrow` chokepoint that
    stamps tenancy.
    """
    task_id = self.request.id or "merge_uploads"
    emit(
        task_id,
        "received",
        f"merge {left_identifier} {how} {right_identifier} ON {on}",
    )
    ctx = _build_context(
        user_id=user_id,
        workspace_id=workspace_id,
        project_id=project_id,
        run_id=task_id,
    )

    try:
        with use_context(ctx):
            from aqp.data import iceberg_catalog

            try:
                import duckdb
                import pyarrow as pa
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("duckdb + pyarrow required for merge") from exc

            conn = duckdb.connect(":memory:", read_only=False)
            left_view = iceberg_catalog.iceberg_to_duckdb_view(conn, left_identifier)
            right_view = iceberg_catalog.iceberg_to_duckdb_view(conn, right_identifier)
            if not left_view or not right_view:
                raise ValueError("could not register iceberg views")

            join_cols = ", ".join(f'"{c}"' for c in on if c)
            if not join_cols:
                raise ValueError("merge requires at least one ON column")

            how_sql = how.lower().strip()
            if how_sql not in ("inner", "left", "right", "outer", "full"):
                raise ValueError(f"unsupported join kind: {how!r}")
            how_clause = "FULL OUTER" if how_sql in ("outer", "full") else how_sql.upper()

            query = (
                f'SELECT * FROM "{left_view}" {how_clause} JOIN "{right_view}" '
                f"USING ({join_cols})"
            )
            arrow_tbl = conn.execute(query).arrow()

            target_namespace = _silver_namespace_for(workspace_id)
            iceberg_catalog.ensure_namespace(target_namespace)
            target_identifier = f"{target_namespace}.{target_table}"
            iceberg_catalog.drop_table(target_identifier)
            iceberg_catalog.append_arrow(
                target_identifier,
                arrow_tbl,
                context=ctx,
                shared=False,
            )

        result_payload = {
            "ok": True,
            "iceberg_identifier": target_identifier,
            "namespace": target_namespace,
            "table_name": target_table,
            "rows_written": int(arrow_tbl.num_rows),
        }
        emit_done(task_id, result_payload)
        return result_payload
    except Exception as exc:  # noqa: BLE001
        logger.exception("merge_uploaded_datasets failed")
        emit_error(task_id, str(exc))
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _silver_namespace_for(workspace_id: str | None) -> str:
    import re

    cleaned = re.sub(r"[^a-zA-Z0-9]+", "", workspace_id or "default").lower()
    return f"aqp_silver_user_uploads_ws_{cleaned[:24] or 'default'}"


def _mark_dataset_status(
    *,
    iceberg_identifier: str,
    workspace_id: str | None,
    status: str,
    extras: dict[str, Any] | None = None,
) -> None:
    """Update the placeholder :class:`DatasetCatalog` row's status."""
    try:
        from datetime import datetime

        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import DatasetCatalog

        with get_session() as session:
            row = (
                session.execute(
                    select(DatasetCatalog).where(
                        DatasetCatalog.iceberg_identifier == iceberg_identifier
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                return
            if (
                row.workspace_id is not None
                and workspace_id is not None
                and row.workspace_id != workspace_id
            ):
                # Defensive: never mutate a row outside the active workspace.
                return
            meta = dict(row.meta or {})
            meta["status"] = status
            if extras:
                meta.update(extras)
            row.meta = meta
            row.updated_at = datetime.utcnow()
    except Exception:  # noqa: BLE001
        logger.debug("could not update dataset status to %s", status, exc_info=True)
