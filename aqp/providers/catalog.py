"""Fetcher catalog — domain path → list of fetchers with policy.

Provides a simple registry keyed by a ``domain_path`` (``equity.info``,
``fundamentals.balance_sheet``, ``ownership.insider``, ``macro.treasury_rates``,
…). Each domain path carries an ordered list of :class:`Fetcher` subclasses;
callers can pick one by policy (``primary``, ``fallback``, ``by_vendor``,
``by_cost_tier``).

The catalog mirrors the existing ``DataSource`` policy knobs for fundamentals
(``AQP_FUNDAMENTALS_PROVIDER=auto|alpha_vantage|yfinance``) so switching from
an adapter-flavored flow to a fetcher-flavored flow is transparent.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from aqp.providers.base import CostTier, Fetcher

logger = logging.getLogger(__name__)


class FetcherCatalog:
    """Domain-path → ordered fetcher list."""

    def __init__(self) -> None:
        self._by_domain: dict[str, list[type[Fetcher]]] = {}

    def register(
        self,
        domain_path: str,
        fetcher: type[Fetcher],
        *,
        priority: int = 0,
    ) -> None:
        """Register ``fetcher`` under ``domain_path`` at a given priority.

        Higher priority wins when the catalog resolves the ``primary``
        fetcher; ties fall back to declaration order.
        """
        bucket = self._by_domain.setdefault(domain_path, [])
        # Tuple of (priority, fetcher) stored inline so we can sort cheaply.
        # We keep the public surface list[type[Fetcher]]; priority is sidecar.
        bucket.append(fetcher)
        # Annotate so the priority is discoverable without a second dict.
        setattr(fetcher, "_catalog_priority", priority)
        bucket.sort(key=lambda f: getattr(f, "_catalog_priority", 0), reverse=True)

    def get(self, domain_path: str) -> list[type[Fetcher]]:
        return list(self._by_domain.get(domain_path, []))

    def domains(self) -> list[str]:
        return sorted(self._by_domain.keys())

    def describe(self) -> dict[str, list[dict[str, Any]]]:
        return {
            domain: [f.describe() for f in fetchers]
            for domain, fetchers in sorted(self._by_domain.items())
        }

    def primary(self, domain_path: str) -> type[Fetcher] | None:
        bucket = self.get(domain_path)
        return bucket[0] if bucket else None

    def pick(
        self,
        domain_path: str,
        *,
        vendor: str | None = None,
        max_cost_tier: CostTier | None = None,
    ) -> type[Fetcher] | None:
        """Pick a fetcher honoring vendor and cost-tier preferences.

        If ``vendor`` is provided, return the first fetcher with matching
        ``vendor_key`` (or ``None`` if no match). Otherwise return the first
        fetcher whose ``cost_tier`` is at or below ``max_cost_tier``.
        """
        candidates = self.get(domain_path)
        if not candidates:
            return None
        if vendor is not None:
            wanted = vendor.lower()
            for f in candidates:
                if f.vendor_key.lower() == wanted:
                    return f
            return None
        if max_cost_tier is not None:
            order = _COST_TIER_ORDER
            limit = order.get(max_cost_tier, len(order))
            for f in candidates:
                if order.get(f.cost_tier, len(order)) <= limit:
                    return f
            return None
        return candidates[0]

    def fanout(
        self,
        domain_path: str,
        params: dict[str, Any],
        credentials: dict[str, str] | None = None,
        *,
        max_cost_tier: CostTier | None = None,
    ) -> Iterable[tuple[type[Fetcher], Any, Exception | None]]:
        """Yield ``(fetcher, result, error)`` triples for every eligible fetcher.

        Useful for provider-diversity fallbacks and for diffing multi-provider
        responses in research flows.
        """
        for f in self.get(domain_path):
            if max_cost_tier is not None:
                order = _COST_TIER_ORDER
                if order.get(f.cost_tier, len(order)) > order.get(max_cost_tier, len(order)):
                    continue
            try:
                result = f.fetch(params=params, credentials=credentials)
                yield f, result, None
            except Exception as exc:  # pragma: no cover — surface to caller
                logger.warning("fetcher %s failed", f.__qualname__, exc_info=True)
                yield f, None, exc


_COST_TIER_ORDER: dict[CostTier, int] = {
    CostTier.NONE: 0,
    CostTier.FREE: 1,
    CostTier.FREEMIUM: 2,
    CostTier.PAID: 3,
    CostTier.PREMIUM: 4,
    CostTier.ENTERPRISE: 5,
}


# Module-wide default catalog. Callers that need isolation (tests, multi-tenant)
# can build their own :class:`FetcherCatalog` and inject it.
_fetcher_catalog = FetcherCatalog()


def fetcher_catalog() -> FetcherCatalog:
    """Return the process-wide default :class:`FetcherCatalog`."""
    return _fetcher_catalog


def register_fetcher(
    domain_path: str,
    fetcher: type[Fetcher] | None = None,
    *,
    priority: int = 0,
):
    """Register a fetcher via decorator or direct call.

    Usage::

        @register_fetcher("fundamentals.balance_sheet", priority=10)
        class FmpBalanceSheetFetcher(Fetcher[BalanceSheetQueryParams, list[BalanceSheetData]]): ...
    """

    def _apply(target: type[Fetcher]) -> type[Fetcher]:
        _fetcher_catalog.register(domain_path, target, priority=priority)
        return target

    if fetcher is None:
        return _apply
    return _apply(fetcher)


def pick_fetcher(
    domain_path: str,
    *,
    vendor: str | None = None,
    max_cost_tier: CostTier | None = None,
) -> type[Fetcher] | None:
    return _fetcher_catalog.pick(domain_path, vendor=vendor, max_cost_tier=max_cost_tier)


def list_fetchers(domain_path: str | None = None) -> list[type[Fetcher]]:
    if domain_path is None:
        out: list[type[Fetcher]] = []
        for bucket in _fetcher_catalog._by_domain.values():
            out.extend(bucket)
        return out
    return _fetcher_catalog.get(domain_path)
