"""Stage user uploads + dispatch the materialise step.

The :class:`DatasetManager` is the single seam between the
``POST /datasets/upload`` HTTP endpoint and the existing
:class:`~aqp.data.pipelines.IngestionPipeline`. It deliberately does
**not** stream into Iceberg synchronously: an upload is fast (write the
bytes to object storage), but materialising the bytes into a Parquet/
Iceberg table is potentially long. The manager therefore:

1. Validates the filename + content-type hint.
2. Streams bytes into the configured object store under a workspace-
   scoped key (or the local-first filesystem fallback).
3. Registers a placeholder :class:`DatasetCatalog` row owned by the
   uploader, so the dataset is queryable in the UI immediately with
   ``status="ingesting"``.
4. Dispatches a Celery task (``aqp.tasks.dataset_upload_tasks
   .materialise_uploaded_dataset``) that runs the existing
   :class:`IngestionPipeline.run_path` against the staged bytes,
   binding the request context for tenancy stamping along the way.

Storage backends:

- **MinIO / S3** — when ``settings.minio_endpoint_url`` is set and
  ``boto3`` is importable.
- **Local filesystem** — fallback that writes under
  ``settings.data_dir / "uploads" / "workspace=<ws>" / "<dataset_id>"``.

Both backends produce the same :class:`StagedUpload` shape so the
downstream materialise task is storage-agnostic.

The manager is **per-workspace by construction**: every method takes a
:class:`RequestContext` (or reads it from the request-scoped
contextvar) and refuses to operate on rows that belong to a different
workspace.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import IO, Any

from sqlalchemy import select

from aqp.auth.context import RequestContext
from aqp.auth.contextvars import get_context_or_default
from aqp.config import settings
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog

logger = logging.getLogger(__name__)


_SAFE_NAME = re.compile(r"[^a-z0-9._-]+")
_ALLOWED_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".ndjson",
    ".parquet",
    ".pq",
    ".feather",
    ".arrow",
    ".xlsx",
    ".xls",
}


def _safe_filename(name: str) -> str:
    """Reduce *name* to a safe lowercase ascii slug, preserving extension."""
    base = (name or "upload").strip().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = base.lower()
    base = _SAFE_NAME.sub("_", base).strip("_")
    return base or "upload"


def _table_name_from_filename(filename: str) -> str:
    """Strip the extension and snake-case the remainder."""
    stem = Path(filename).stem.lower()
    stem = _SAFE_NAME.sub("_", stem).strip("_")
    return stem or "uploaded"


def _workspace_slug(workspace_id: str | None) -> str:
    """Return a stable ID-derived slug suitable for Iceberg namespaces.

    Iceberg namespaces are restricted to ``[a-z0-9_]``; UUIDs
    work fine once the dashes are stripped. We prepend ``ws_`` so
    namespaces always sort with a stable prefix.
    """
    if not workspace_id:
        return "ws_default"
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "", workspace_id).lower()
    return f"ws_{cleaned[:24] or 'default'}"


@dataclass(frozen=True)
class StagedUpload:
    """Where the uploaded bytes landed + how the materialise task can read them."""

    dataset_id: str
    storage_uri: str  # ``s3://...`` or ``file://...``
    object_key: str | None
    filename: str
    bytes_written: int
    content_type: str | None
    workspace_id: str | None
    backend: str  # ``minio`` | ``local``


@dataclass(frozen=True)
class UploadResult:
    """Response shape returned to the HTTP endpoint."""

    dataset_id: str
    catalog_id: str
    status: str
    storage_uri: str
    backend: str
    filename: str
    iceberg_identifier: str
    namespace: str
    table_name: str
    task_id: str | None = None
    bytes_written: int = 0
    workspace_id: str | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class MergeJob:
    """Descriptor for a workspace-scoped relational merge."""

    left_id: str
    right_id: str
    on: tuple[str, ...]
    how: str  # ``inner`` | ``left`` | ``right`` | ``outer``
    target_table: str
    workspace_id: str
    project_id: str | None
    requester_user_id: str | None


# ---------------------------------------------------------------------------
# Storage backends
# ---------------------------------------------------------------------------


class _LocalUploadBackend:
    """Filesystem fallback used when MinIO/S3 isn't configured."""

    name = "local"

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def stage(
        self,
        *,
        workspace_id: str | None,
        dataset_id: str,
        filename: str,
        stream: IO[bytes],
        content_type: str | None,
    ) -> StagedUpload:
        ws = workspace_id or "default"
        dest = self.base_dir / f"workspace={ws}" / dataset_id / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = 0
        with dest.open("wb") as f:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                bytes_written += len(chunk)
        return StagedUpload(
            dataset_id=dataset_id,
            storage_uri=dest.resolve().as_uri(),
            object_key=str(dest.relative_to(self.base_dir)),
            filename=filename,
            bytes_written=bytes_written,
            content_type=content_type,
            workspace_id=workspace_id,
            backend=self.name,
        )


class _MinioUploadBackend:
    """MinIO / S3 backend — used when ``settings.minio_endpoint_url`` is set."""

    name = "minio"

    def __init__(self, *, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self._client = None

    def _client_lazy(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
            from botocore.client import Config
        except ImportError as exc:  # pragma: no cover - dep guard
            raise RuntimeError(
                "boto3 is required for MinIO uploads; install via the [sources] extra"
            ) from exc

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        # Ensure the bucket exists. MinIO returns NoSuchBucket; AWS S3
        # returns NoSuchBucket as well. Either way we create it.
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self.bucket)
            except Exception:  # noqa: BLE001
                logger.debug("create_bucket %s failed (may already exist)", self.bucket, exc_info=True)
        return self._client

    def stage(
        self,
        *,
        workspace_id: str | None,
        dataset_id: str,
        filename: str,
        stream: IO[bytes],
        content_type: str | None,
    ) -> StagedUpload:
        client = self._client_lazy()
        ws = workspace_id or "default"
        key = f"workspace={ws}/uploads/{dataset_id}/{filename}"
        extra: dict[str, str] = {}
        if content_type:
            extra["ContentType"] = content_type
        client.upload_fileobj(stream, self.bucket, key, ExtraArgs=extra or None)
        try:
            head = client.head_object(Bucket=self.bucket, Key=key)
            bytes_written = int(head.get("ContentLength") or 0)
        except Exception:  # noqa: BLE001
            bytes_written = 0
        return StagedUpload(
            dataset_id=dataset_id,
            storage_uri=f"s3://{self.bucket}/{key}",
            object_key=key,
            filename=filename,
            bytes_written=bytes_written,
            content_type=content_type,
            workspace_id=workspace_id,
            backend=self.name,
        )


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class DatasetManager:
    """Thin orchestrator over the upload backends + Iceberg materialiser."""

    def __init__(
        self,
        *,
        backend: _LocalUploadBackend | _MinioUploadBackend,
        bronze_namespace_prefix: str = "aqp_bronze_user_uploads",
    ) -> None:
        self.backend = backend
        self.bronze_namespace_prefix = bronze_namespace_prefix

    # -- upload -----------------------------------------------------------

    def upload_file(
        self,
        *,
        stream: IO[bytes],
        filename: str,
        content_type: str | None,
        context: RequestContext | None = None,
        dataset_name: str | None = None,
        description: str | None = None,
    ) -> UploadResult:
        """Stage *stream* and dispatch the materialise task.

        Returns immediately with ``status="ingesting"`` and the Celery
        task id; the frontend can subscribe to the existing progress
        bus to drive the upload UI.
        """
        ctx = context if context is not None else get_context_or_default()
        ext = Path(filename).suffix.lower()
        if ext and ext not in _ALLOWED_EXTENSIONS:
            raise ValueError(
                f"unsupported upload extension {ext!r}; allowed: "
                + ", ".join(sorted(_ALLOWED_EXTENSIONS))
            )

        dataset_id = str(uuid.uuid4())
        safe_name = _safe_filename(filename)
        table_name = _table_name_from_filename(safe_name)
        ws_slug = _workspace_slug(ctx.workspace_id)
        namespace = f"{self.bronze_namespace_prefix}_{ws_slug}"
        identifier = f"{namespace}.{table_name}"

        staged = self.backend.stage(
            workspace_id=ctx.workspace_id,
            dataset_id=dataset_id,
            filename=safe_name,
            stream=stream,
            content_type=content_type,
        )

        catalog_id = self._upsert_placeholder_catalog(
            ctx=ctx,
            identifier=identifier,
            display_name=dataset_name or safe_name,
            description=description,
            staged=staged,
        )

        task_id = self._dispatch_materialise(
            staged=staged,
            ctx=ctx,
            namespace=namespace,
            table_name=table_name,
        )

        return UploadResult(
            dataset_id=dataset_id,
            catalog_id=catalog_id,
            status="ingesting",
            storage_uri=staged.storage_uri,
            backend=staged.backend,
            filename=staged.filename,
            iceberg_identifier=identifier,
            namespace=namespace,
            table_name=table_name,
            task_id=task_id,
            bytes_written=staged.bytes_written,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
        )

    def _upsert_placeholder_catalog(
        self,
        *,
        ctx: RequestContext,
        identifier: str,
        display_name: str,
        description: str | None,
        staged: StagedUpload,
    ) -> str:
        """Create / update a :class:`DatasetCatalog` row in ``status=ingesting``."""
        now = datetime.utcnow()
        with get_session() as session:
            existing = (
                session.execute(
                    select(DatasetCatalog).where(
                        DatasetCatalog.iceberg_identifier == identifier
                    )
                )
                .scalars()
                .first()
            )
            if existing is None:
                row_kwargs: dict[str, Any] = dict(
                    name=display_name,
                    provider="user_upload",
                    domain="data.user_upload",
                    iceberg_identifier=identifier,
                    medallion_layer="bronze",
                    description=description,
                    tags=["user-upload", staged.backend],
                    meta={
                        "upload_dataset_id": staged.dataset_id,
                        "storage_uri": staged.storage_uri,
                        "object_key": staged.object_key,
                        "filename": staged.filename,
                        "bytes_written": staged.bytes_written,
                        "status": "ingesting",
                    },
                    load_mode="managed",
                    source_uri=staged.storage_uri,
                    created_at=now,
                    updated_at=now,
                )
                if ctx.user_id:
                    row_kwargs["owner_user_id"] = ctx.user_id
                if ctx.workspace_id:
                    row_kwargs["workspace_id"] = ctx.workspace_id
                if ctx.project_id:
                    row_kwargs["project_id"] = ctx.project_id
                row = DatasetCatalog(**row_kwargs)
                session.add(row)
                session.flush()
                return str(row.id)
            existing.description = description or existing.description
            meta = dict(existing.meta or {})
            meta.update(
                {
                    "upload_dataset_id": staged.dataset_id,
                    "storage_uri": staged.storage_uri,
                    "object_key": staged.object_key,
                    "filename": staged.filename,
                    "bytes_written": staged.bytes_written,
                    "status": "ingesting",
                }
            )
            existing.meta = meta
            existing.source_uri = staged.storage_uri
            existing.updated_at = now
            return str(existing.id)

    def _dispatch_materialise(
        self,
        *,
        staged: StagedUpload,
        ctx: RequestContext,
        namespace: str,
        table_name: str,
    ) -> str | None:
        """Hand the staged file off to the Celery materialise task.

        Returns the task id so the route can stream progress; returns
        ``None`` when Celery isn't available (e.g. unit tests).
        """
        try:
            from aqp.tasks.dataset_upload_tasks import materialise_uploaded_dataset

            async_result = materialise_uploaded_dataset.delay(
                staged_uri=staged.storage_uri,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
                user_id=ctx.user_id,
                namespace=namespace,
                table_name=table_name,
                content_type=staged.content_type,
                dataset_id=staged.dataset_id,
            )
            return str(async_result.id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Could not dispatch materialise_uploaded_dataset; running inline fallback",
                exc_info=True,
            )
            return None

    # -- merge ------------------------------------------------------------

    def merge_datasets(
        self,
        *,
        left_id: str,
        right_id: str,
        on: list[str],
        how: str = "inner",
        target_table: str | None = None,
        context: RequestContext | None = None,
    ) -> str:
        """Schedule a relational merge between two workspace datasets.

        Validates that both datasets belong to the active workspace,
        derives a target table name in the same bronze namespace as
        the left dataset, and dispatches a Celery task to perform the
        merge with PyArrow + DuckDB.

        Returns the Celery task id (or raises if both datasets cannot
        be located in the active workspace).
        """
        ctx = context if context is not None else get_context_or_default()
        if not ctx.workspace_id:
            raise ValueError("merge requires an active workspace")

        with get_session() as session:
            left = session.get(DatasetCatalog, left_id)
            right = session.get(DatasetCatalog, right_id)
            if left is None or right is None:
                raise ValueError(f"dataset not found: left={left_id!r}, right={right_id!r}")
            for label, row in (("left", left), ("right", right)):
                if row.workspace_id is not None and row.workspace_id != ctx.workspace_id:
                    raise PermissionError(
                        f"{label} dataset {row.iceberg_identifier!r} belongs to a different workspace"
                    )
            left_identifier = str(left.iceberg_identifier or "")
            right_identifier = str(right.iceberg_identifier or "")

        if not left_identifier or not right_identifier:
            raise ValueError("merge requires both datasets to have an Iceberg identifier")

        merge_target = (target_table or f"merge_{uuid.uuid4().hex[:8]}").lower()
        merge_target = _SAFE_NAME.sub("_", merge_target).strip("_") or "merge_dataset"

        try:
            from aqp.tasks.dataset_upload_tasks import merge_uploaded_datasets

            async_result = merge_uploaded_datasets.delay(
                left_identifier=left_identifier,
                right_identifier=right_identifier,
                on=list(on),
                how=str(how),
                target_table=merge_target,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
                user_id=ctx.user_id,
            )
            return str(async_result.id)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"could not dispatch merge task: {exc}") from exc


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_MANAGER: DatasetManager | None = None


def get_dataset_manager() -> DatasetManager:
    """Return a process-wide :class:`DatasetManager` (lazy-init)."""
    global _MANAGER
    if _MANAGER is not None:
        return _MANAGER

    endpoint = (settings.minio_endpoint_url or settings.s3_endpoint_url or "").strip()
    access = (settings.minio_access_key or settings.s3_access_key or "").strip()
    secret = (settings.minio_secret_key or settings.s3_secret_key or "").strip()
    bucket = (settings.minio_datasets_bucket or "aqp-datasets").strip()

    if endpoint and access and secret:
        backend: _LocalUploadBackend | _MinioUploadBackend = _MinioUploadBackend(
            endpoint=endpoint,
            access_key=access,
            secret_key=secret,
            bucket=bucket,
        )
    else:
        base = Path(settings.data_dir) / "uploads"
        base.mkdir(parents=True, exist_ok=True)
        backend = _LocalUploadBackend(base_dir=base)

    _MANAGER = DatasetManager(backend=backend)
    return _MANAGER


__all__ = [
    "DatasetManager",
    "MergeJob",
    "StagedUpload",
    "UploadResult",
    "get_dataset_manager",
]
