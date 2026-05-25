"""HuggingFaceAdapter — Hub-aware model + tokenizer + example puller.

Wraps ``huggingface_hub.snapshot_download`` so the platform-wide
``CacheHandler`` reads from one canonical local directory. Resolves
the HF auth token through :class:`CredentialResolver`
(``CredentialKey("huggingface", "api_token")``) — never reads
``HUGGINGFACE_HUB_TOKEN`` directly.

The adapter honours ``settings.ml_hf_hub_offline``: when set, it
refuses to talk to the Hub and only returns cached snapshots.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from aqp_models.adapters.base import PullResult, RegistryAdapter

logger = logging.getLogger(__name__)


class HuggingFaceAdapter(RegistryAdapter):
    """HuggingFace Hub puller."""

    adapter_kind = "huggingface"
    default_cache_subdir = "external_models"

    def pull(
        self,
        model_name: str,
        *,
        revision: str | None = None,
        cache_dir: str | None = None,
        include_examples: bool = False,
    ) -> PullResult:
        started = datetime.utcnow()
        cache = self.cache_dir_for(cache_dir)
        try:
            offline = _bool_setting("ml_hf_hub_offline", False)
        except Exception:  # noqa: BLE001
            offline = False

        try:
            from huggingface_hub import snapshot_download
        except Exception as exc:  # noqa: BLE001
            return PullResult(
                ok=False,
                adapter_kind=self.adapter_kind,
                model_name=model_name,
                revision=revision,
                local_path=None,
                error=f"huggingface_hub unavailable: {exc}",
                elapsed_ms=_elapsed_ms(started),
            )

        token = self.resolve_token(purpose="api_token")
        warnings: list[str] = []
        try:
            local_path_str = snapshot_download(
                repo_id=model_name,
                revision=revision,
                cache_dir=str(cache),
                token=token,
                local_files_only=offline,
            )
        except Exception as exc:  # noqa: BLE001
            return PullResult(
                ok=False,
                adapter_kind=self.adapter_kind,
                model_name=model_name,
                revision=revision,
                local_path=None,
                error=str(exc),
                warnings=warnings,
                elapsed_ms=_elapsed_ms(started),
            )

        local_path = Path(local_path_str)
        size_bytes = _dir_size(local_path)
        examples_loaded = 0
        if include_examples:
            examples_loaded = self.import_examples(model_name, target_dir=str(local_path))

        return PullResult(
            ok=True,
            adapter_kind=self.adapter_kind,
            model_name=model_name,
            revision=revision,
            local_path=local_path,
            size_bytes=size_bytes,
            examples_loaded=examples_loaded,
            metadata={
                "offline": bool(offline),
                "token_present": bool(token),
                "cache_dir": str(cache),
            },
            warnings=warnings,
            elapsed_ms=_elapsed_ms(started),
        )

    def import_examples(self, model_name: str, *, target_dir: str | None = None) -> int:
        """Best-effort: most HF repos ship example notebooks under ``examples/``.

        ``snapshot_download`` already pulls every file inside the repo
        when no ``allow_patterns`` is specified, so the examples are
        local on disk already. The count is informational; the loader
        leaves the files in place so notebooks can be opened directly.
        """
        if not target_dir:
            return 0
        target = Path(target_dir)
        if not target.exists():
            return 0
        examples = list(target.rglob("examples/*"))
        if not examples:
            examples = list(target.rglob("notebooks/*"))
        return len(examples)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dir_size(path: Path) -> int:
    total = 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += int(entry.stat().st_size)
        except OSError:
            continue
    return total


def _bool_setting(name: str, default: bool) -> bool:
    try:
        from aqp.config import settings

        return bool(getattr(settings, name, default))
    except Exception:  # noqa: BLE001
        return bool(default)


def _elapsed_ms(started: datetime) -> float:
    return float(round((datetime.utcnow() - started).total_seconds() * 1000.0, 3))


__all__ = ["HuggingFaceAdapter"]
