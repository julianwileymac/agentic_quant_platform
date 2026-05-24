"""Shared CredentialResolver helper for the monolith's curated fetchers.

Migration path (Phase 1 of the plan):

Pre-Phase-1: ``settings.polygon_api_key`` / ``settings.tiingo_api_key`` /
``settings.alpha_vantage_api_key`` / ``settings.quandl_api_key`` /
``settings.coingecko_api_key`` were read DIRECTLY by the matching
fetcher. That violates root AGENTS.md rule 26 (all credentials
through :class:`CredentialResolver`) and rule 7 (no `os.environ`
reads outside `scripts/`).

Post-Phase-1: every curated fetcher calls
:func:`resolve_vendor_api_key` which walks the resolver chain in
priority order:

1. :class:`BrokerCredentialStore` (priority 4, BYOK per rule 55)
2. :class:`UserOAuthTokenStore` (priority 5, when relevant)
3. The remaining stores (Vault, cloud KMS, file, env)

The legacy ``settings.<vendor>_api_key`` fallback is preserved
strictly so existing deployments keep working — the platform
operator can rotate the legacy global key out incrementally.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_vendor_api_key(
    *,
    provider: str,
    label: str = "primary",
    field: str = "api_key",
    settings_attr: str | None = None,
    settings_alt_attrs: tuple[str, ...] = (),
) -> str | None:
    """Resolve a vendor API key with full rule-26 compliance.

    Parameters
    ----------
    provider:
        Vendor slug (``"polygon"``, ``"tiingo"``, ``"alpha_vantage"``,
        ``"quandl"``, ``"coingecko"``).
    label:
        Per-user key label (defaults to ``"primary"``).
    field:
        Which credential field holds the API key (default ``"api_key"``).
    settings_attr:
        Legacy settings attribute name to fall back on, e.g.
        ``"polygon_api_key"``. Only used when the resolver chain
        returns nothing.
    settings_alt_attrs:
        Alternative settings attributes (for legacy env-var aliases).
    """
    try:
        from aqp.credentials import get_resolver
        from aqp.credentials.protocol import CredentialKey
    except Exception as exc:  # noqa: BLE001
        logger.debug("credential resolver unavailable: %s", exc)
        return _settings_fallback(settings_attr, settings_alt_attrs)

    service = f"{provider}:{label}" if label else provider
    try:
        bundle = get_resolver().resolve(
            CredentialKey(service=service, purpose="broker")
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "credential resolver failed for %s/%s: %s", provider, label, exc
        )
        bundle = None
    if bundle is not None:
        value = bundle.get(field)
        if value:
            return str(value)

    # Some BYOK providers used a slightly different field name historically
    # (api_key vs token); try the common aliases.
    if bundle is not None:
        for alt in ("token", "key", "access_token"):
            if alt == field:
                continue
            value = bundle.get(alt)
            if value:
                return str(value)

    return _settings_fallback(settings_attr, settings_alt_attrs)


def _settings_fallback(
    settings_attr: str | None,
    settings_alt_attrs: tuple[str, ...],
) -> str | None:
    if not settings_attr and not settings_alt_attrs:
        return None
    try:
        from aqp.config import settings as _settings
    except Exception:  # noqa: BLE001
        return None
    for attr in (settings_attr, *settings_alt_attrs):
        if not attr:
            continue
        value = getattr(_settings, attr, None)
        if value:
            return str(value)
    return None


__all__ = ["resolve_vendor_api_key"]
