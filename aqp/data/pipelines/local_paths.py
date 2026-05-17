"""Resolve local ingest paths across host and container filesystems.

The local ingest API accepts user-provided paths. In Docker deployments the
caller often supplies a host path (for example ``C:/Users/...``) while API
and worker run inside Linux containers (for example ``/host-data/...``).

`AQP_LOCAL_INGEST_PATH_MAP` bridges that gap using comma-separated mappings:

    C:/Users/name/Data=>/host-data,C:/Users/name/Downloads=>/host-downloads

Each mapping rewrites a host-prefix match to a container-prefix candidate.
Resolution checks the original path first, then mapped candidates, and returns
the first existing path.
"""
from __future__ import annotations

from pathlib import Path

from aqp.config import settings


class LocalPathResolutionError(ValueError):
    """Raised when a local ingest path cannot be resolved to an existing path."""


def _normalize_path(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) >= 2 and text[1] == ":":
        text = text[0].lower() + text[1:]
    if text != "/" and text.endswith("/"):
        text = text.rstrip("/")
    return text


def _is_windows_like(path_text: str) -> bool:
    return len(path_text) >= 2 and path_text[1] == ":"


def _path_has_prefix(path_text: str, prefix_text: str, *, casefold: bool) -> bool:
    left = path_text.casefold() if casefold else path_text
    right = prefix_text.casefold() if casefold else prefix_text
    return left == right or left.startswith(f"{right}/")


def _mapped_candidates(raw_path: str) -> list[str]:
    normalized_raw = _normalize_path(raw_path)
    is_win = _is_windows_like(normalized_raw)
    out: list[str] = []
    for host_prefix, container_prefix in settings.local_ingest_path_map_pairs:
        host_norm = _normalize_path(host_prefix)
        if not host_norm:
            continue
        casefold = is_win or _is_windows_like(host_norm)
        if not _path_has_prefix(normalized_raw, host_norm, casefold=casefold):
            continue
        suffix = normalized_raw[len(host_norm) :].lstrip("/")
        container_norm = _normalize_path(container_prefix)
        mapped = f"{container_norm}/{suffix}" if suffix else container_norm
        out.append(mapped)
    return out


def resolve_local_ingest_path(path: str | Path, *, require_exists: bool = True) -> Path:
    """Resolve host/container path variants and return the first existing one.

    When ``require_exists`` is true and no candidate exists, raises
    :class:`LocalPathResolutionError` with an actionable message.
    """
    raw = str(path).strip()
    if not raw:
        raise LocalPathResolutionError("path is required")

    attempts: list[str] = []
    candidates: list[Path] = []

    direct = Path(raw).expanduser()
    candidates.append(direct)
    attempts.append(str(direct))

    for mapped in _mapped_candidates(raw):
        mapped_path = Path(mapped).expanduser()
        if str(mapped_path) in attempts:
            continue
        candidates.append(mapped_path)
        attempts.append(str(mapped_path))

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    fallback = candidates[-1] if len(candidates) > 1 else direct
    if not require_exists:
        return fallback

    mapping_hint = ", ".join(
        f"{host}=>{container}" for host, container in settings.local_ingest_path_map_pairs
    ) or "(none configured)"
    raise LocalPathResolutionError(
        "path does not exist in this runtime; "
        f"input={raw!r}; checked={attempts}; "
        f"AQP_LOCAL_INGEST_PATH_MAP={mapping_hint}"
    )


__all__ = ["LocalPathResolutionError", "resolve_local_ingest_path"]
