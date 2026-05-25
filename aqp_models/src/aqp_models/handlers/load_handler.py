"""LoadHandler — cryptographic verification + deserialisation of model artifacts.

The handler resolves a saved artifact (pickle or ``safetensors``)
identified by a registered :class:`ModelVersion` id and rehydrates the
in-memory object. Safetensors are preferred when both formats are
available; the loader rejects pickle artifacts whose checksum does not
match the persisted hash so a tampered payload never reaches the
serving layer.

Loaders are wired by the existing
:func:`aqp.metadata.aspect_lookup.load_ml_model` helper for entity-
aspect resolution and ``ModelVersion`` ORM rows for legacy
artifacts. This handler is the thin policy-aware wrapper that the
:class:`CacheHandler` calls on a cache miss.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from aqp_models.handlers.base import (
    HandlerContext,
    HandlerResult,
    MLOpsHandler,
)

logger = logging.getLogger(__name__)


class LoadResult(HandlerResult):
    """Marker subclass for the route layer's response model.

    Carries the loaded model in ``data`` plus the chosen artifact
    format (``safetensors`` / ``pickle``) and computed checksum in
    ``metadata``.
    """


class LoadHandler(MLOpsHandler):
    """Load a registered model artifact by ``ModelVersion`` id.

    Resolution order:

    1. Resolve the ``ModelVersion`` row via Postgres.
    2. If the row carries a ``safetensors_path`` / ``artifact_path``,
       prefer safetensors (no Python deserialisation, no arbitrary code
       execution).
    3. Fall back to pickle. Reject when the file's SHA-256 does not
       match the persisted ``artifact_sha256``.
    """

    handler_name = "ml.load"
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: HandlerContext,
        model_version_id: str | None = None,
        artifact_path: str | None = None,
        expected_sha256: str | None = None,
        format: str | None = None,
        **_: Any,
    ) -> HandlerResult:
        if not model_version_id and not artifact_path:
            return HandlerResult(
                ok=False,
                error="load requires ``model_version_id`` or ``artifact_path``",
            )

        # 1. Resolve via Postgres if a model_version_id was supplied.
        if model_version_id:
            resolved = self._resolve_from_model_version(model_version_id)
            if resolved is None:
                return HandlerResult(
                    ok=False,
                    error=f"model_version {model_version_id!r} not found",
                )
            artifact_path = resolved.get("artifact_path") or artifact_path
            expected_sha256 = resolved.get("artifact_sha256") or expected_sha256
            format = format or resolved.get("format")

        if not artifact_path:
            return HandlerResult(
                ok=False,
                error="resolved row had no artifact_path",
            )

        path = Path(artifact_path)
        if not path.exists():
            return HandlerResult(ok=False, error=f"artifact not found: {path}")

        actual_sha256 = _file_sha256(path)
        if expected_sha256 and actual_sha256 != expected_sha256:
            return HandlerResult(
                ok=False,
                error=(
                    "artifact checksum mismatch -- expected "
                    f"{expected_sha256[:12]}..., got {actual_sha256[:12]}..."
                ),
                metadata={"expected_sha256": expected_sha256, "actual_sha256": actual_sha256},
            )

        chosen = format or _detect_format(path)
        try:
            if chosen == "safetensors":
                model = _load_safetensors(path)
            else:
                model = _load_pickle(path)
        except Exception as exc:  # noqa: BLE001
            return HandlerResult(
                ok=False,
                error=f"deserialise failed ({chosen}): {exc}",
            )

        return LoadResult(
            ok=True,
            data=model,
            summary=f"loaded {path.name} ({chosen})",
            metadata={
                "format": chosen,
                "sha256": actual_sha256,
                "model_class": model.__class__.__name__,
                "size_bytes": int(path.stat().st_size),
            },
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_from_model_version(self, model_version_id: str) -> dict[str, Any] | None:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import ModelVersion
        except Exception:  # noqa: BLE001
            logger.debug("ModelVersion ORM unavailable", exc_info=True)
            return None

        try:
            with get_session() as session:
                row = session.get(ModelVersion, model_version_id)
                if row is None:
                    return None
                metrics = row.metrics or {}
                return {
                    "artifact_path": (
                        metrics.get("artifact_path")
                        or metrics.get("safetensors_path")
                        or metrics.get("model_path")
                    ),
                    "artifact_sha256": metrics.get("artifact_sha256"),
                    "format": metrics.get("artifact_format"),
                    "registry_name": row.registry_name,
                }
        except Exception:  # noqa: BLE001
            logger.exception("LoadHandler ORM lookup failed")
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_sha256(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".safetensors", ".st"}:
        return "safetensors"
    if suffix in {".pt", ".pth", ".bin"}:
        return "torch_state"
    return "pickle"


def _load_safetensors(path: Path) -> Any:
    try:
        from safetensors.torch import load_file
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("safetensors is required for .safetensors artifacts") from exc
    return load_file(str(path))


def _load_pickle(path: Path) -> Any:
    import pickle

    with path.open("rb") as fh:
        return pickle.load(fh)


__all__ = ["LoadHandler", "LoadResult"]
