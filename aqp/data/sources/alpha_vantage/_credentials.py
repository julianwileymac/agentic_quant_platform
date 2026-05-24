"""Alpha Vantage API-key resolution (rule-26 + rule-7 compliant).

Pre-Phase-1: read directly from ``os.environ`` (rule 7 violation)
and ``settings.alpha_vantage_api_key`` (rule 26 violation).

Post-Phase-1: walks the canonical
:class:`aqp.credentials.CredentialResolver` chain first
(BYOK + Vault + cloud KMS + file + env-via-store), then falls back
to the legacy ``settings.alpha_vantage_api_key`` field and the
historical file paths for backwards compatibility with bootstrap
deployments. No direct ``os.environ`` reads remain.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from aqp.config import settings
from aqp.data.fetchers.api._resolver import resolve_vendor_api_key
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
    credential_label: str = "primary",
) -> str:
    """Resolve an API key via :class:`CredentialResolver` chain.

    Order:

    1. Explicit ``api_key`` argument (caller override).
    2. :class:`BrokerCredentialStore` via
       :func:`resolve_vendor_api_key` — BYOK per rule 55.
    3. ``settings.alpha_vantage_api_key`` (legacy fallback during
       the migration window).
    4. Historical mounted-secret file paths.

    All ``os.environ`` reads are deliberately removed (rule 7).
    The :class:`EnvSecretStore` inside the resolver chain still
    surfaces env-var-backed credentials, so the historical
    ``AQP_ALPHA_VANTAGE_API_KEY`` env var path still works — it
    just goes through the proper store, not a direct ``os.environ``
    read in this module.
    """
    explicit = str(api_key or "").strip()
    if explicit:
        return explicit

    resolved = resolve_vendor_api_key(
        provider="alpha_vantage",
        label=credential_label,
        settings_attr="alpha_vantage_api_key",
    )
    if resolved:
        return str(resolved).strip()

    key_file = (
        file_path
        or getattr(settings, "alpha_vantage_api_key_file", "")
        or ""
    )
    value = _read_first_existing([key_file, *(extra_paths or ()), *DEFAULT_KEY_PATHS])
    if value:
        return value
    if strict:
        raise InvalidApiKeyError(
            "AQP_ALPHA_VANTAGE_API_KEY is not configured; mint a BYOK key with "
            "`aqp keys mint --service alpha_vantage` or set "
            "`AQP_ALPHA_VANTAGE_API_KEY` so the EnvSecretStore can resolve it."
        )
    return ""


__all__ = ["DEFAULT_KEY_PATHS", "load_api_key"]
