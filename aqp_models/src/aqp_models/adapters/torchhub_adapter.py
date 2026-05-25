"""TorchHubAdapter — allow-list-protected TorchHub puller.

TorchHub executes downloaded Python from arbitrary GitHub repos. The
platform refuses to do this against an unrestricted universe because a
malicious model could introduce code that runs inside the serving
worker. The adapter requires every ``model_name`` to be listed in
:data:`DEFAULT_ALLOWLIST` (or in an operator-supplied allowlist
sourced via :class:`CredentialResolver`).

When the underlying ``torch.hub`` call returns a module path or a file
on disk we verify the SHA-256 against the allowlist entry before
caching it under ``settings.data_dir / external_models / torchhub``.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from aqp_models.adapters.base import PullResult, RegistryAdapter

logger = logging.getLogger(__name__)


# A small, conservative default allow-list. Operators override via the
# credential store at ``CredentialKey("torchhub", "allowlist")`` (a JSON
# array of ``"<repo>/<model>": "<sha256>"`` entries) so additions can be
# audited without redeploys.
DEFAULT_ALLOWLIST: dict[str, str | None] = {
    "pytorch/vision/resnet50": None,
    "pytorch/vision/resnet18": None,
    "pytorch/vision/mobilenet_v2": None,
    "pytorch/fairseq/transformer_wmt_en_de": None,
}


class TorchHubAdapter(RegistryAdapter):
    """TorchHub puller with checksum verification."""

    adapter_kind = "torchhub"
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
        offline = _bool_setting("ml_torchhub_offline", False)
        warnings: list[str] = []

        allowlist = self._resolve_allowlist()
        if model_name not in allowlist:
            return PullResult(
                ok=False,
                adapter_kind=self.adapter_kind,
                model_name=model_name,
                revision=revision,
                local_path=None,
                error=(
                    f"TorchHub model {model_name!r} is not on the platform"
                    " allow-list; add it via CredentialResolver before pulling."
                ),
                elapsed_ms=_elapsed_ms(started),
            )

        try:
            import torch

            # Hub cache controls — torch.hub honours TORCH_HOME / set_dir.
            try:
                torch.hub.set_dir(str(cache))
            except Exception:  # noqa: BLE001
                pass

            if offline:
                warnings.append("offline mode: loading from local cache only")
            parts = model_name.split("/")
            if len(parts) < 3:
                raise ValueError(
                    "TorchHub model_name must be '<owner>/<repo>/<model>',"
                    " got " + model_name
                )
            repo = "/".join(parts[:2])
            model_id = parts[2]
            obj = torch.hub.load(
                repo,
                model_id,
                source="github",
                force_reload=not offline and bool(self._force_reload(revision)),
                trust_repo=False,  # NEVER auto-trust; allowlist gated this call.
                verbose=False,
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

        # Persist the in-memory model into the cache so the SHA-256 can be
        # verified against the allowlist.
        try:
            local_path = self._materialise(obj, cache, model_name)
        except Exception as exc:  # noqa: BLE001
            return PullResult(
                ok=False,
                adapter_kind=self.adapter_kind,
                model_name=model_name,
                revision=revision,
                local_path=None,
                error=f"materialise failed: {exc}",
                warnings=warnings,
                elapsed_ms=_elapsed_ms(started),
            )

        sha = _sha256_file(local_path)
        expected = allowlist.get(model_name)
        if expected and sha != expected:
            local_path.unlink(missing_ok=True)
            return PullResult(
                ok=False,
                adapter_kind=self.adapter_kind,
                model_name=model_name,
                revision=revision,
                local_path=None,
                error=(
                    f"SHA-256 mismatch for {model_name!r}: expected "
                    f"{expected[:12]}..., got {sha[:12]}..."
                ),
                warnings=warnings,
                elapsed_ms=_elapsed_ms(started),
            )

        return PullResult(
            ok=True,
            adapter_kind=self.adapter_kind,
            model_name=model_name,
            revision=revision,
            local_path=local_path,
            sha256=sha,
            size_bytes=int(local_path.stat().st_size),
            examples_loaded=0,
            metadata={"offline": bool(offline), "allowlist_match": True},
            warnings=warnings,
            elapsed_ms=_elapsed_ms(started),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_allowlist(self) -> dict[str, str | None]:
        """Merge the default allow-list with operator-supplied entries."""
        out = dict(DEFAULT_ALLOWLIST)
        try:
            from aqp.credentials.protocol import CredentialKey
            from aqp.credentials.resolver import get_resolver

            cred = get_resolver().resolve(
                CredentialKey(service=self.adapter_kind, purpose="allowlist"),
            )
            raw = cred.fields.get("entries")
            if raw:
                import json

                supplied = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(supplied, dict):
                    out.update(supplied)
        except Exception:  # noqa: BLE001
            logger.debug("torchhub allowlist resolution failed", exc_info=True)
        return out

    def _force_reload(self, revision: str | None) -> bool:
        return bool(revision)

    def _materialise(self, obj: Any, cache: Path, model_name: str) -> Path:
        import torch

        safe = model_name.replace("/", "__")
        target = cache / f"{safe}.pt"
        if isinstance(obj, torch.nn.Module):
            torch.save(obj.state_dict(), str(target))
        else:
            # Fallback: pickle the bare object so subsequent loads are
            # deterministic. Allowed only because the allowlist gate
            # already ruled out untrusted sources.
            import pickle

            with target.open("wb") as fh:
                pickle.dump(obj, fh)
        return target


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _bool_setting(name: str, default: bool) -> bool:
    try:
        from aqp.config import settings

        return bool(getattr(settings, name, default))
    except Exception:  # noqa: BLE001
        return bool(default)


def _elapsed_ms(started: datetime) -> float:
    return float(round((datetime.utcnow() - started).total_seconds() * 1000.0, 3))


__all__ = ["DEFAULT_ALLOWLIST", "TorchHubAdapter"]
