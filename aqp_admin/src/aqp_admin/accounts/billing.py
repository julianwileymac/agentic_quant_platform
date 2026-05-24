"""Billing facade. Routes mutating calls through a provider in `aqp_admin.providers`."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BillingSummary:
    org_id: str
    period: str
    amount_cents: int
    currency: str


class BillingService:
    """Stub. Real impl delegates to a registered billing provider."""

    async def summary(self, org_id: str, period: str) -> BillingSummary:
        return BillingSummary(org_id=org_id, period=period, amount_cents=0, currency="USD")
