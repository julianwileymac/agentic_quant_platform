"""Replay-cache strategy: VCR.py-style cassette replay.

In ``replay`` mode every :meth:`check` returns ``allow=True`` with
``decision="cached"`` IF the request hash exists in the cassette
store, otherwise raises. This is the canonical "backtest must not
burn live quota" guarantee.

In ``record`` mode every call delegates to the inner strategy and
the actual HTTP response is written to the cassette store
out-of-band (the Envoy proxy + Airbyte CDK wrapper handle the
write; this strategy only handles the quota accounting decision).
"""
from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from aqp_ratelimit.exceptions import RateLimitExceeded
from aqp_ratelimit.models import Decision, ReserveOutcome
from aqp_ratelimit.strategies.base import IngestionRateLimitStrategy

logger = logging.getLogger(__name__)


class ReplayMode(StrEnum):
    OFF = "off"
    RECORD = "record"
    REPLAY = "replay"


class ReplayCacheStrategy(IngestionRateLimitStrategy):
    """Compose with another strategy to enable cassette-replay backtests."""

    strategy_kind = "replay_cache"
    strategy_alias = "ReplayCacheStrategy"
    strategy_priority = 3  # checked before everything else

    def __init__(
        self,
        *,
        inner: IngestionRateLimitStrategy,
        mode: ReplayMode | str = ReplayMode.OFF,
        cache_index: Any | None = None,
    ) -> None:
        self._inner = inner
        self._mode = ReplayMode(str(mode))
        self._cache = cache_index

    @property
    def mode(self) -> ReplayMode:
        return self._mode

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def check(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
        n_tokens: int = 1,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        if self._mode == ReplayMode.OFF:
            return self._inner.check(
                user_id=user_id,
                service=service,
                key_id=key_id,
                n_tokens=n_tokens,
                ctx=ctx,
            )
        request_hash = (ctx or {}).get("request_hash") if ctx else None
        if self._mode == ReplayMode.REPLAY:
            if request_hash and self._cache and self._cache.exists(request_hash):
                return Decision(
                    allow=True,
                    remaining=0.0,
                    capacity=0.0,
                    refill_rate=0.0,
                    service=service,
                    key_id=key_id,
                    user_id=user_id,
                    metadata={"decision": "cached", "request_hash": request_hash},
                )
            raise RateLimitExceeded(
                service=service,
                key_id=key_id,
                remaining=0.0,
                requested=n_tokens,
                retry_after_ms=0,
            )
        # RECORD mode debits the inner bucket so live quota usage is honest.
        return self._inner.check(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=n_tokens,
            ctx=ctx,
        )

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
        if self._mode == ReplayMode.REPLAY:
            return ReserveOutcome(
                allow=True,
                reservation_id="replay-no-op",
                requested=n_tokens,
                remaining=0.0,
                capacity=0.0,
                ttl_s=ttl_s,
                service=service,
                key_id=key_id,
                user_id=user_id,
                metadata={"decision": "cached"},
            )
        return self._inner.reserve(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=n_tokens,
            ttl_s=ttl_s,
            ctx=ctx,
        )

    def release(self, *, reservation_id: str) -> None:
        if reservation_id == "replay-no-op":
            return
        self._inner.release(reservation_id=reservation_id)

    def status(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
    ) -> Decision:
        decision = self._inner.status(user_id=user_id, service=service, key_id=key_id)
        decision.metadata["replay_mode"] = self._mode.value
        return decision


__all__ = ["ReplayCacheStrategy", "ReplayMode"]
