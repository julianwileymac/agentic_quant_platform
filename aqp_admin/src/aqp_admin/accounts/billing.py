"""Billing facade — delegates to a registered :class:`BillingProvider`.

The provider abstraction sits between the route layer and the
concrete vendor SDKs (Stripe, etc.). New billing surfaces register
through the provider; the BFF only handles aggregation + audit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BillingSummary:
    org_id: str
    period: str
    amount_cents: int
    currency: str
    provider: str
    line_items: tuple[dict[str, Any], ...] = ()


@runtime_checkable
class BillingProvider(Protocol):
    @property
    def alias(self) -> str: ...

    async def summary(self, org_id: str, period: str) -> BillingSummary: ...


class BillingService:
    """Aggregator over one or more :class:`BillingProvider` instances."""

    def __init__(
        self,
        providers: tuple[BillingProvider, ...] = (),
    ) -> None:
        self._providers: tuple[BillingProvider, ...] = tuple(providers)

    def add_provider(self, provider: BillingProvider) -> None:
        self._providers = (*self._providers, provider)

    async def summary(self, org_id: str, period: str) -> BillingSummary:
        """Return the first non-empty provider summary or an empty default."""
        for provider in self._providers:
            try:
                return await provider.summary(org_id, period)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "billing provider %s summary failed: %s",
                    getattr(provider, "alias", provider),
                    exc,
                )
                continue
        return BillingSummary(
            org_id=org_id,
            period=period,
            amount_cents=0,
            currency="USD",
            provider="none",
        )

    async def summary_all(
        self,
        org_id: str,
        period: str,
    ) -> list[BillingSummary]:
        out: list[BillingSummary] = []
        for provider in self._providers:
            try:
                out.append(await provider.summary(org_id, period))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "billing provider %s summary failed: %s",
                    getattr(provider, "alias", provider),
                    exc,
                )
        return out


__all__ = ["BillingProvider", "BillingService", "BillingSummary"]
