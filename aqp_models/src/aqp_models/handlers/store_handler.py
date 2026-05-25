"""StoreHandler — async upload of saved artifacts to the platform's object store.

This is intentionally a thin orchestrator. Concrete object-store
backends (local filesystem, S3, MinIO, NFS share) plug in via callable
backends; the default is the local filesystem store backed by
``settings.aqp_data_dir / "ml_store"`` so dev / test loops work
without external infra.

The handler appends lineage metadata to every upload so the
``data.catalog.lineage`` MCP tool can trace ``ModelVersion`` ->
artifact -> downstream backtest / paper / deployment.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from aqp_models.handlers.base import (
    HandlerContext,
    HandlerResult,
    MLOpsHandler,
)

logger = logging.getLogger(__name__)


StoreBackend = Callable[[Path, str, dict[str, Any]], dict[str, Any]]


class StoreResult(HandlerResult):
    """Marker subclass for the route layer's response model."""


@dataclass(slots=True)
class _LocalFsBackend:
    """Default backend: copy the file into ``base_dir`` and return the path."""

    base_dir: Path

    def __call__(
        self,
        src: Path,
        object_key: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        target = self.base_dir / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        return {
            "backend": "local_fs",
            "uri": f"file://{target}",
            "object_key": object_key,
            "size_bytes": int(target.stat().st_size),
            "metadata": dict(metadata),
        }


class StoreHandler(MLOpsHandler):
    """Push a saved artifact + sidecars into the object store.

    Args to :meth:`run`:

    - ``source_path`` — file produced by :class:`SaveHandler`.
    - ``object_key`` — relative key inside the store
      (e.g. ``models/lgb_returns_1d/v3.safetensors``).
    - ``metadata`` — extra fields persisted alongside the upload and
      emitted to the lineage event.
    """

    handler_name = "ml.store"
    required_scopes = ("data:write",)
    mutates = True

    def __init__(self, *, backend: StoreBackend | None = None) -> None:
        super().__init__()
        self._backend = backend or _LocalFsBackend(_default_store_dir())

    def run(
        self,
        *,
        ctx: HandlerContext,
        source_path: str | None = None,
        object_key: str | None = None,
        metadata: dict[str, Any] | None = None,
        include_sidecar: bool = True,
        **_: Any,
    ) -> HandlerResult:
        if not source_path:
            return HandlerResult(ok=False, error="store requires ``source_path``")
        if not object_key:
            return HandlerResult(ok=False, error="store requires ``object_key``")

        src = Path(source_path)
        if not src.exists():
            return HandlerResult(ok=False, error=f"source not found: {src}")

        meta = {
            "stored_at": datetime.utcnow().isoformat(),
            "workspace_id": ctx.workspace_id,
            "project_id": ctx.project_id,
            "actor": ctx.actor,
            "actor_kind": ctx.actor_kind,
            **(metadata or {}),
        }

        uploaded = self._backend(src, object_key, meta)
        uploaded_sidecar: dict[str, Any] | None = None
        if include_sidecar:
            sidecar = src.with_suffix(src.suffix + ".sha256")
            if sidecar.exists():
                sidecar_key = f"{object_key}.sha256"
                uploaded_sidecar = self._backend(sidecar, sidecar_key, meta)

        return StoreResult(
            ok=True,
            data={
                "uploaded": uploaded,
                "sidecar": uploaded_sidecar,
            },
            summary=f"stored {object_key}",
            metadata={
                "object_key": object_key,
                "backend": uploaded.get("backend"),
                "uri": uploaded.get("uri"),
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_store_dir() -> Path:
    try:
        from aqp.config import settings

        data_dir = Path(getattr(settings, "data_dir", "data"))
    except Exception:  # noqa: BLE001
        data_dir = Path("data")
    target = data_dir / "ml_store"
    target.mkdir(parents=True, exist_ok=True)
    return target


__all__ = ["StoreHandler", "StoreResult"]
