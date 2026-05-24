"""ResolverBackedConfigProvider — feed Airbyte configs from CredentialResolver.

Connector YAML never carries plaintext API keys. Instead, the
config block references the BYOK credential by ``provider:label``
and the provider resolves the actual secret value via
:class:`aqp.credentials.CredentialResolver` at sync time, drawing
from :class:`aqp.credentials.stores.broker_credential_store.BrokerCredentialStore`
(priority 4 per root AGENTS.md rule 55).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_vendor_credential(
    *,
    provider: str,
    label: str = "primary",
    field: str = "api_key",
) -> str | None:
    """Resolve a single field of a BYOK broker credential.

    Returns ``None`` when the resolver chain has no opinion;
    callers raise a clear error in that case rather than fall
    through silently.
    """
    try:
        from aqp.credentials import get_resolver
        from aqp.credentials.protocol import CredentialKey
    except Exception as exc:  # noqa: BLE001
        logger.warning("credentials chain unavailable: %s", exc)
        return None
    service = f"{provider}:{label}" if label else provider
    try:
        bundle = get_resolver().resolve(
            CredentialKey(service=service, purpose="broker")
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "credential resolve failed for %s/%s: %s", provider, label, exc
        )
        return None
    if bundle is None:
        return None
    return bundle.get(field)


class ResolverBackedConfigProvider:
    """Wraps a connector config dict, injecting resolved secrets just-in-time.

    Usage::

        provider = ResolverBackedConfigProvider(base_config={
            "tickers": ["AAPL", "MSFT"],
            "lookback_days": 30,
        })
        cfg = provider.materialize(
            owner_user_id="user_abc",
            provider="polygon",
            label="primary",
            field="api_key",
            config_key="api_key",
        )
        # cfg == {
        #   "tickers": [...],
        #   "lookback_days": 30,
        #   "api_key": "<resolved secret value>",
        #   "_aqp_owner_user_id": "user_abc",
        #   "_aqp_rate_limit_key_id": "primary",
        # }
    """

    def __init__(self, *, base_config: dict[str, Any] | None = None) -> None:
        self._base = dict(base_config or {})

    def materialize(
        self,
        *,
        owner_user_id: str,
        provider: str,
        label: str = "primary",
        field: str = "api_key",
        config_key: str = "api_key",
        rate_limit_service: str | None = None,
    ) -> dict[str, Any]:
        """Return a materialized config dict with the secret injected."""
        out = dict(self._base)
        value = resolve_vendor_credential(
            provider=provider, label=label, field=field
        )
        if value:
            out[config_key] = value
        else:
            logger.warning(
                "ResolverBackedConfigProvider: no credential for %s/%s",
                provider,
                label,
            )
        out["_aqp_owner_user_id"] = owner_user_id
        out["_aqp_rate_limit_key_id"] = label
        if rate_limit_service:
            out["_aqp_rate_limit_service"] = rate_limit_service
        return out


__all__ = ["ResolverBackedConfigProvider", "resolve_vendor_credential"]
