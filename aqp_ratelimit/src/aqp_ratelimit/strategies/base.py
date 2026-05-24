"""IngestionRateLimitStrategy ABC + self-registering metaclass.

Mirrors :class:`aqp.tenancy.protocol.TenancyStrategyMeta` and
:class:`aqp.credentials.protocol.SecretStoreMeta`. Subclasses set
``strategy_kind`` (the dispatch key the
:class:`IngestionRateLimitFactory` matches against
``settings.ratelimit_default_strategy`` or per-tenant overrides) and
the metaclass calls :func:`aqp.core.registry.register` automatically.

Surface every strategy exposes:

- :meth:`check(user_id, service, key_id, n_tokens=1, ctx=None) -> Decision`
  — atomic non-blocking token-bucket check + debit. Fast path on
  every outbound vendor call.
- :meth:`reserve(user_id, service, key_id, n_tokens, ttl_s, ctx=None) -> ReserveOutcome`
  — multi-token preflight reservation for partitioned backfills.
  Tokens auto-release on TTL expiry if the reservation isn't
  consumed.
- :meth:`release(reservation_id) -> None` — explicit release.
- :meth:`status(user_id, service, key_id) -> Decision` — read-only
  bucket snapshot for the UI / CLI.
- :meth:`describe() -> dict` — diagnostic surface (no DSNs, no
  vault paths).
"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from typing import Any, ClassVar

from aqp_ratelimit.models import Decision, ReserveOutcome

logger = logging.getLogger(__name__)


INGESTION_RATELIMIT_STRATEGY_KIND = "ingestion_ratelimit_strategy"


class IngestionRateLimitMeta(ABCMeta):
    """Metaclass that auto-registers concrete :class:`IngestionRateLimitStrategy` subclasses.

    Skips abstract bases (``__abstract_strategy__ = True`` or names
    starting with ``Base`` / ``_``).
    """

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_strategy__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        kind = getattr(cls, "strategy_kind", None)
        if not kind:
            return cls
        alias = getattr(cls, "strategy_alias", None) or cls.__name__
        try:
            from aqp.core.registry import register

            register(
                name=alias,
                kind=INGESTION_RATELIMIT_STRATEGY_KIND,
                source=str(kind),
            )(cls)
        except Exception:  # noqa: BLE001
            logger.debug(
                "IngestionRateLimitStrategy auto-registration failed for %s",
                name,
                exc_info=True,
            )
        return cls


class IngestionRateLimitStrategy(metaclass=IngestionRateLimitMeta):
    """Pluggable per-(user, service, key_id) rate-limit strategy.

    Subclasses set:

    - ``strategy_kind`` — one of ``redis_token_bucket``, ``in_memory``,
      ``leaky_bucket``, ``per_agent``, ``replay_cache``. The dispatch
      key the :class:`IngestionRateLimitFactory` matches against
      ``settings.ratelimit_default_strategy``.
    - ``strategy_alias`` (optional) — registry alias; defaults to
      the class name.
    - ``strategy_priority`` (optional) — used by composite strategies
      (e.g., the :class:`PerAgentStrategy` chains a per-user strategy
      after itself).
    """

    __abstract_strategy__: ClassVar[bool] = True

    strategy_kind: ClassVar[str] = ""
    strategy_alias: ClassVar[str | None] = None
    strategy_priority: ClassVar[int] = 50

    @abstractmethod
    def check(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
        n_tokens: int = 1,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        """Atomic non-blocking token-bucket check + debit.

        Returns a :class:`Decision` with ``allow=False`` and
        ``retry_after_ms`` populated when the bucket can't satisfy
        the request. Callers honour ``retry_after_ms`` rather than
        burning the bucket with retries.
        """

    @abstractmethod
    def reserve(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
        n_tokens: int,
        ttl_s: int,
        ctx: dict[str, Any] | None = None,
    ) -> ReserveOutcome:
        """Multi-token preflight reservation for partitioned backfills.

        The tokens are debited immediately; the caller has ``ttl_s``
        seconds to either consume them (via subsequent :meth:`check`
        calls keyed on ``reservation_id``) or :meth:`release` them.
        Tokens auto-release on TTL expiry to bound the worst-case
        starvation window.
        """

    @abstractmethod
    def release(self, *, reservation_id: str) -> None:
        """Release a previously :meth:`reserve`-d batch of tokens.

        Idempotent: releasing an already-released reservation is a
        no-op. Releasing an unknown reservation is also a no-op
        (the TTL likely fired first).
        """

    @abstractmethod
    def status(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
    ) -> Decision:
        """Read-only bucket snapshot for the UI / CLI.

        Does NOT debit; ``decision.allow`` reflects whether a single
        ``n_tokens=1`` :meth:`check` would currently succeed.
        """

    def describe(self) -> dict[str, Any]:
        """Diagnostic surface (no DSNs, no vault paths)."""
        return {
            "kind": self.strategy_kind,
            "alias": self.strategy_alias or self.__class__.__name__,
            "priority": self.strategy_priority,
        }


def list_ratelimit_strategy_classes() -> dict[str, type[IngestionRateLimitStrategy]]:
    """Return ``{alias: class}`` for every registered strategy."""
    try:
        from aqp.core.registry import list_by_kind
    except Exception:  # pragma: no cover - bootstrap before aqp.core available
        return {}
    out: dict[str, type[IngestionRateLimitStrategy]] = {}
    for alias, cls in list_by_kind(INGESTION_RATELIMIT_STRATEGY_KIND).items():
        if isinstance(cls, type) and issubclass(cls, IngestionRateLimitStrategy):
            out[alias] = cls
    return out


__all__ = [
    "INGESTION_RATELIMIT_STRATEGY_KIND",
    "IngestionRateLimitMeta",
    "IngestionRateLimitStrategy",
    "list_ratelimit_strategy_classes",
]
