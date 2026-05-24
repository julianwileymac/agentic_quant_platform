"""In-memory token-bucket strategy.

Used in tests, on developer laptops (`aqp context use local`), and in
the `local` profile of branch deployments. Single-process only; for
multi-worker deployments use :class:`RedisTokenBucketStrategy`.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from aqp_ratelimit.models import Decision, ReserveOutcome
from aqp_ratelimit.strategies.base import IngestionRateLimitStrategy


@dataclass
class _Bucket:
    capacity: float
    refill_rate: float
    tokens: float
    last_refill: float


@dataclass
class _Reservation:
    bucket_key: str
    tokens: int
    expires_at: float
    capacity: float = 0.0


class InMemoryStrategy(IngestionRateLimitStrategy):
    """Process-local token-bucket strategy."""

    strategy_kind = "in_memory"
    strategy_alias = "InMemoryStrategy"
    strategy_priority = 90  # lower is preferred; fallback only

    DEFAULT_CAPACITY: float = 60.0
    DEFAULT_REFILL_RATE: float = 1.0  # 60 RPM at refill_rate=1/sec

    def __init__(
        self,
        *,
        capacity: float = DEFAULT_CAPACITY,
        refill_rate: float = DEFAULT_REFILL_RATE,
    ) -> None:
        self._default_capacity = float(capacity)
        self._default_refill_rate = float(refill_rate)
        self._buckets: dict[str, _Bucket] = {}
        self._reservations: dict[str, _Reservation] = {}
        self._lock = threading.RLock()

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
        key = self._bucket_key(user_id, service, key_id)
        capacity, refill_rate = self._resolve_policy(service, ctx)
        with self._lock:
            bucket = self._get_or_create(key, capacity, refill_rate)
            self._refill_locked(bucket)
            if bucket.tokens < n_tokens:
                if bucket.refill_rate > 0:
                    retry_ms = int(
                        max(
                            0.0,
                            (n_tokens - bucket.tokens) / bucket.refill_rate * 1000.0,
                        )
                    )
                else:
                    # Refill rate of 0 means the bucket never replenishes;
                    # surface a large but finite sentinel so callers can
                    # log + back off without a hard-error path.
                    retry_ms = 3_600_000  # 1 hour
                return Decision(
                    allow=False,
                    remaining=bucket.tokens,
                    capacity=bucket.capacity,
                    refill_rate=bucket.refill_rate,
                    retry_after_ms=retry_ms,
                    service=service,
                    key_id=key_id,
                    user_id=user_id,
                )
            bucket.tokens -= n_tokens
            return Decision(
                allow=True,
                remaining=bucket.tokens,
                capacity=bucket.capacity,
                refill_rate=bucket.refill_rate,
                retry_after_ms=0,
                service=service,
                key_id=key_id,
                user_id=user_id,
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
        decision = self.check(
            user_id=user_id,
            service=service,
            key_id=key_id,
            n_tokens=n_tokens,
            ctx=ctx,
        )
        if not decision.allow:
            return ReserveOutcome(
                allow=False,
                requested=n_tokens,
                remaining=decision.remaining,
                capacity=decision.capacity,
                ttl_s=ttl_s,
                service=service,
                key_id=key_id,
                user_id=user_id,
            )
        rsv_id = str(uuid.uuid4())
        with self._lock:
            self._reservations[rsv_id] = _Reservation(
                bucket_key=self._bucket_key(user_id, service, key_id),
                tokens=n_tokens,
                expires_at=time.monotonic() + ttl_s,
                capacity=decision.capacity,
            )
        return ReserveOutcome(
            allow=True,
            reservation_id=rsv_id,
            requested=n_tokens,
            remaining=decision.remaining,
            capacity=decision.capacity,
            ttl_s=ttl_s,
            service=service,
            key_id=key_id,
            user_id=user_id,
        )

    def release(self, *, reservation_id: str) -> None:
        with self._lock:
            rsv = self._reservations.pop(reservation_id, None)
            if rsv is None:
                return
            bucket = self._buckets.get(rsv.bucket_key)
            if bucket is None:
                return
            bucket.tokens = min(bucket.capacity, bucket.tokens + rsv.tokens)

    def status(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
    ) -> Decision:
        key = self._bucket_key(user_id, service, key_id)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return Decision(
                    allow=True,
                    remaining=self._default_capacity,
                    capacity=self._default_capacity,
                    refill_rate=self._default_refill_rate,
                    service=service,
                    key_id=key_id,
                    user_id=user_id,
                )
            self._refill_locked(bucket)
            return Decision(
                allow=bucket.tokens >= 1,
                remaining=bucket.tokens,
                capacity=bucket.capacity,
                refill_rate=bucket.refill_rate,
                service=service,
                key_id=key_id,
                user_id=user_id,
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _bucket_key(self, user_id: str, service: str, key_id: str) -> str:
        return f"aqp:rl:{user_id}:{service}:{key_id}"

    def _resolve_policy(
        self,
        service: str,
        ctx: dict[str, Any] | None,
    ) -> tuple[float, float]:
        if ctx is None:
            return self._default_capacity, self._default_refill_rate
        return (
            float(ctx.get("capacity", self._default_capacity)),
            float(ctx.get("refill_rate", self._default_refill_rate)),
        )

    def _get_or_create(
        self,
        key: str,
        capacity: float,
        refill_rate: float,
    ) -> _Bucket:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(
                capacity=capacity,
                refill_rate=refill_rate,
                tokens=capacity,
                last_refill=time.monotonic(),
            )
            self._buckets[key] = bucket
        return bucket

    def _refill_locked(self, bucket: _Bucket) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - bucket.last_refill)
        bucket.tokens = min(
            bucket.capacity,
            bucket.tokens + elapsed * bucket.refill_rate,
        )
        bucket.last_refill = now


__all__ = ["InMemoryStrategy"]
