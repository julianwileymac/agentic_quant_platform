"""Stripe billing provider.

Real implementation behind the ``stripe`` optional dependency. The
Stripe SDK is imported lazily so the admin BFF can boot without the
SDK installed (local dev / CI). Credentials resolve through the
platform-core ``CredentialResolver`` chain (rule 26).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aqp_admin.accounts.billing import BillingSummary
from aqp_admin.integrations.broker import EnvSecretStore
from aqp_platform_core.credentials.protocol import (
    Credential,
    CredentialKey,
    SecretStore,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StripeCharge:
    customer_id: str
    amount_cents: int
    currency: str
    status: str


class StripeProvider:
    """Stripe-backed :class:`BillingProvider`.

    Constructor accepts a :class:`CredentialKey` so different
    deployments can rotate keys independently. The secret resolves
    through the same chain used by every other admin integration.
    """

    alias = "stripe"

    def __init__(
        self,
        *,
        credential_key: CredentialKey | None = None,
        secret_stores: tuple[SecretStore, ...] = (),
    ) -> None:
        self._credential_key = credential_key or CredentialKey(
            service="stripe", purpose="secret_key"
        )
        self._stores: tuple[SecretStore, ...] = tuple(
            secret_stores or (EnvSecretStore(),)
        )
        self._secret: str | None = None

    def _resolve_secret(self) -> str:
        if self._secret is not None:
            return self._secret
        # The EnvSecretStore from the broker layer normalises to
        # AQP_ADMIN_M2M_<SERVICE>_<PURPOSE>_CLIENT_SECRET. We honour
        # the same shape here; explicit STRIPE_SECRET_KEY is the
        # convenience override below.
        for store in self._stores:
            try:
                cred = store.get(self._credential_key)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "stripe credential lookup via %s failed: %s",
                    store.__class__.__name__,
                    exc,
                )
                continue
            if cred is not None and (secret := cred.get("client_secret")):
                self._secret = str(secret)
                return self._secret
        # Local-dev convenience env var.
        import os

        env_value = os.environ.get("STRIPE_SECRET_KEY")
        if env_value:
            self._secret = env_value
            return env_value
        raise RuntimeError(
            "Stripe secret not resolvable via CredentialResolver chain"
        )

    async def summary(self, org_id: str, period: str) -> BillingSummary:
        """Return a brief usage summary (skeleton).

        The real impl fans out to the Stripe ``Invoice`` + ``Subscription``
        APIs; the skeleton returns a deterministic placeholder so the
        admin UI can render the section without a live Stripe key.
        """
        try:
            self._resolve_secret()
        except RuntimeError:
            logger.info(
                "stripe summary returning placeholder — no secret configured"
            )
            return BillingSummary(
                org_id=org_id,
                period=period,
                amount_cents=0,
                currency="USD",
                provider=self.alias,
                line_items=(),
            )
        # Lazy import so the SDK stays optional.
        try:
            import stripe  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "stripe SDK not installed (pip install 'aqp-admin[stripe]'); "
                "returning placeholder"
            )
            return BillingSummary(
                org_id=org_id,
                period=period,
                amount_cents=0,
                currency="USD",
                provider=self.alias,
            )
        stripe.api_key = self._secret  # type: ignore[attr-defined]
        # Skeleton: real impl iterates Customers + Invoices for the
        # period window and aggregates totals.
        return BillingSummary(
            org_id=org_id,
            period=period,
            amount_cents=0,
            currency="USD",
            provider=self.alias,
        )


__all__ = ["StripeCharge", "StripeProvider"]
