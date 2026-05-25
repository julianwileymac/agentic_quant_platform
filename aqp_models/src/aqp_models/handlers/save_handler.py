"""SaveHandler — serialise an in-memory model's state to disk.

Two output formats:

- **safetensors** — preferred. Only for objects that expose a torch
  ``state_dict()`` (PyTorch zoo models). Safetensors is byte-deterministic
  and cannot execute arbitrary code on load.
- **pickle** — fallback. Used for sklearn / xgboost / qlib wrappers that
  do not have a torch state dict. The handler always emits a side-car
  ``.sha256`` file so :class:`LoadHandler` can verify provenance.

The handler does NOT push to the object store — that is
:class:`StoreHandler`'s responsibility. Keeping these separate lets
``save`` run quickly on the worker while ``store`` runs async.
"""
from __future__ import annotations

import hashlib
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

from aqp_models.handlers.base import (
    HandlerContext,
    HandlerResult,
    MLOpsHandler,
)

logger = logging.getLogger(__name__)


class SaveResult(HandlerResult):
    """Marker subclass for the route layer's response model."""


class SaveHandler(MLOpsHandler):
    """Serialise an in-memory model to disk."""

    handler_name = "ml.save"
    required_scopes = ("data:write",)
    mutates = True

    def run(
        self,
        *,
        ctx: HandlerContext,
        model: Any | None = None,
        dest_dir: str | None = None,
        name: str | None = None,
        prefer_safetensors: bool = True,
        **_: Any,
    ) -> HandlerResult:
        if model is None:
            return HandlerResult(ok=False, error="save requires ``model``")
        if not dest_dir:
            return HandlerResult(ok=False, error="save requires ``dest_dir``")

        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        stem = name or f"model_{datetime.utcnow():%Y%m%dT%H%M%S}"

        state_dict = _extract_state_dict(model) if prefer_safetensors else None
        if state_dict is not None:
            try:
                target = dest / f"{stem}.safetensors"
                _write_safetensors(state_dict, target)
                sha = _sha256_file(target)
                _write_sha_sidecar(target, sha)
                return SaveResult(
                    ok=True,
                    data={"path": str(target), "format": "safetensors"},
                    summary=f"saved {target.name}",
                    metadata={
                        "format": "safetensors",
                        "sha256": sha,
                        "size_bytes": int(target.stat().st_size),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("safetensors save failed, falling back to pickle: %s", exc)

        target = dest / f"{stem}.pkl"
        with target.open("wb") as fh:
            pickle.dump(model, fh)
        sha = _sha256_file(target)
        _write_sha_sidecar(target, sha)
        return SaveResult(
            ok=True,
            data={"path": str(target), "format": "pickle"},
            summary=f"saved {target.name}",
            metadata={
                "format": "pickle",
                "sha256": sha,
                "size_bytes": int(target.stat().st_size),
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_state_dict(model: Any) -> dict[str, Any] | None:
    """Return a torch state_dict when the underlying object exposes one."""
    try:
        import torch  # noqa: F401
    except Exception:  # noqa: BLE001
        return None
    candidate = model
    inner = getattr(model, "model", None)
    if inner is not None:
        candidate = inner
    sd = getattr(candidate, "state_dict", None)
    if not callable(sd):
        return None
    try:
        out = sd()
        # Must be a dict of tensors
        if isinstance(out, dict) and out:
            return out
    except Exception:  # noqa: BLE001
        return None
    return None


def _write_safetensors(state_dict: dict[str, Any], path: Path) -> None:
    from safetensors.torch import save_file

    save_file(state_dict, str(path))


def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _write_sha_sidecar(path: Path, sha: str) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{sha}  {path.name}{os.linesep}", encoding="utf-8")


__all__ = ["SaveHandler", "SaveResult"]
