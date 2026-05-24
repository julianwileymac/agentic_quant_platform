"""Stripe billing provider stub.

Stub guards rule 26 (CredentialResolver) and rule 27 (no vendor SDK call
without an explicit indirection). The actual ``stripe`` SDK import lives
behind the ``stripe`` optional-dependency.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StripeCharge:
    customer_id: str
    amount_cents: int
    currency: str
    status: str


class StripeProvider:
    """Stub. Real impl resolves the secret through CredentialResolver."""

    def __init__(self, credential_alias: str = "stripe_secret_key") -> None:
        self.credential_alias = credential_alias

    async def charge(self, customer_id: str, amount_cents: int, currency: str = "USD") -> StripeCharge:
        return StripeCharge(
            customer_id=customer_id,
            amount_cents=amount_cents,
            currency=currency,
            status="stub",
        )
