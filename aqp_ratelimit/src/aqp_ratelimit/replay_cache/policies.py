"""Per-vendor cassette TTL policies.

Blueprint policy:

- ``historical`` (anything older than ``now() - 24h``) — cache
  forever; reuse from cassette without ETag re-validation.
- ``eod`` (previous trading day end-of-day aggregates) — cache 7
  days, then re-validate via ETag.
- ``realtime`` — never cached; live calls only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CachePolicy:
    name: str
    ttl_seconds: int | None  # None = forever
    revalidate_etag: bool = False


HISTORICAL: CachePolicy = CachePolicy(name="historical", ttl_seconds=None)
EOD: CachePolicy = CachePolicy(name="eod", ttl_seconds=7 * 24 * 3600, revalidate_etag=True)
REALTIME: CachePolicy = CachePolicy(name="realtime", ttl_seconds=0)


DEFAULT_TTL_POLICIES: dict[str, CachePolicy] = {
    "historical": HISTORICAL,
    "eod": EOD,
    "realtime": REALTIME,
}


# Regex patterns mapping URL → policy. Order matters — earlier matches win.
_PATTERN_POLICIES: list[tuple[re.Pattern[str], CachePolicy]] = [
    (re.compile(r"/v\d+/aggs/.*/range/\d+/(minute|hour|day)/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})"), HISTORICAL),
    (re.compile(r"/v\d+/trades/.*/(\d{4}-\d{2}-\d{2})"), HISTORICAL),
    (re.compile(r"/v\d+/snapshots/.*"), REALTIME),
    (re.compile(r"/v\d+/last(/|$)"), REALTIME),
    (re.compile(r"/v\d+/grouped/.*"), EOD),
]


def pick_policy_for_url(url: str) -> CachePolicy:
    """Match ``url`` against the policy regex table; default to ``realtime``."""
    for pattern, policy in _PATTERN_POLICIES:
        if pattern.search(url):
            return policy
    return REALTIME


def register_pattern(pattern: str | re.Pattern[str], policy: CachePolicy) -> None:
    """Register a new URL pattern → policy mapping at runtime."""
    compiled = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)
    _PATTERN_POLICIES.insert(0, (compiled, policy))


def all_policies() -> Iterable[CachePolicy]:
    return DEFAULT_TTL_POLICIES.values()


__all__ = [
    "CachePolicy",
    "DEFAULT_TTL_POLICIES",
    "EOD",
    "HISTORICAL",
    "REALTIME",
    "all_policies",
    "pick_policy_for_url",
    "register_pattern",
]
