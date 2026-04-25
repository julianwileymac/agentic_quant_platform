"""Alpha Vantage API-key resolution."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from aqp.config import settings
from aqp.data.sources.alpha_vantage._errors import InvalidApiKeyError


DEFAULT_KEY_PATHS = (
    Path("~/.alphavantage/api_key").expanduser(),
    Path("/var/run/secrets/alphavantage/api-key"),
)


def _read_first_existing(paths: Iterable[str | Path | None]) -> str:
    for raw in paths:
        if not raw:
            continue
        path = Path(str(raw)).expanduser()
        try:
            if path.exists():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except OSError:
            continue
    return ""


def load_api_key(
    api_key: str | None = None,
    *,
    file_path: str | None = None,
    extra_paths: Iterable[str | Path | None] | None = None,
    strict: bool = True,
) -> str:
    """Resolve an API key from explicit args, AQP settings, env, or mounted files."""
    candidates = (
        api_key,
        getattr(settings, "alpha_vantage_api_key", ""),
        os.environ.get("AQP_ALPHA_VANTAGE_API_KEY"),
        os.environ.get("ALPHAVANTAGE_API_KEY"),
        os.environ.get("ALPHA_VANTAGE_API_KEY"),
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value

    key_file = (
        file_path
        or getattr(settings, "alpha_vantage_api_key_file", "")
        or os.environ.get("AQP_ALPHA_VANTAGE_API_KEY_FILE")
        or os.environ.get("ALPHAVANTAGE_API_KEY_FILE")
    )
    value = _read_first_existing([key_file, *(extra_paths or ()), *DEFAULT_KEY_PATHS])
    if value:
        return value
    if strict:
        raise InvalidApiKeyError("AQP_ALPHA_VANTAGE_API_KEY is not configured")
    return ""


__all__ = ["DEFAULT_KEY_PATHS", "load_api_key"]
