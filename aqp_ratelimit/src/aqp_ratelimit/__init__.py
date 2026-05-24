"""Per-(user, service, key_id) rate-limit accounting subsystem.

Public surface:

- :mod:`aqp_ratelimit.strategies` — ABC + metaclass + concrete
  strategies (Redis Lua, in-memory, leaky bucket, per-agent, replay
  cache). Importing this package eagerly registers every concrete
  strategy via :class:`IngestionRateLimitMeta`.
- :mod:`aqp_ratelimit.client` — sync + async clients used by
  Fetchers, Dagster sensors, the CLI, and notebook kernels.
- :mod:`aqp_ratelimit.factory` — singleton resolver
  :func:`get_ratelimit_factory` / :func:`get_ratelimit_client`.
- :mod:`aqp_ratelimit.models` — pydantic :class:`Decision`,
  :class:`ReserveOutcome`, :class:`PolicyDescriptor`,
  :class:`KeyDescriptor`, :class:`LedgerEntry`.
- :mod:`aqp_ratelimit.exceptions` — :class:`RateLimitExceeded`,
  :class:`PolicyNotFoundError`, :class:`KeyRevokedError`.
"""
from __future__ import annotations

import contextlib as _contextlib

from aqp_ratelimit.client import (
    AsyncRateLimitClient,
    RateLimitClient,
    get_async_ratelimit_client,
    get_ratelimit_client,
)
from aqp_ratelimit.exceptions import (
    KeyRevokedError,
    PolicyNotFoundError,
    RateLimitError,
    RateLimitExceeded,
)
from aqp_ratelimit.factory import (
    IngestionRateLimitFactory,
    get_ratelimit_factory,
    reset_ratelimit_factory,
)
from aqp_ratelimit.models import (
    Decision,
    KeyDescriptor,
    LedgerEntry,
    PolicyDescriptor,
    ReserveOutcome,
)
from aqp_ratelimit.strategies.base import (
    INGESTION_RATELIMIT_STRATEGY_KIND,
    IngestionRateLimitMeta,
    IngestionRateLimitStrategy,
    list_ratelimit_strategy_classes,
)

with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp_ratelimit import strategies  # noqa: F401

__all__ = [
    "AsyncRateLimitClient",
    "Decision",
    "INGESTION_RATELIMIT_STRATEGY_KIND",
    "IngestionRateLimitFactory",
    "IngestionRateLimitMeta",
    "IngestionRateLimitStrategy",
    "KeyDescriptor",
    "KeyRevokedError",
    "LedgerEntry",
    "PolicyDescriptor",
    "PolicyNotFoundError",
    "RateLimitClient",
    "RateLimitError",
    "RateLimitExceeded",
    "ReserveOutcome",
    "get_async_ratelimit_client",
    "get_ratelimit_client",
    "get_ratelimit_factory",
    "list_ratelimit_strategy_classes",
    "reset_ratelimit_factory",
]
