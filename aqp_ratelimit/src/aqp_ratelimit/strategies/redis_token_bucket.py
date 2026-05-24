"""Redis Lua token-bucket strategy — canonical multi-worker rate limiter.

Loads the three Lua scripts at process start via ``SCRIPT LOAD`` and
invokes them via ``EVALSHA`` so the per-call latency stays sub-
millisecond per the Redis rate-limiter docs ("Sub-millisecond
latency means the rate check sits on the synchronous request path
without adding meaningful delay, even at millions of requests per
second").
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

from aqp_ratelimit.exceptions import RateLimitError
from aqp_ratelimit.models import Decision, ReserveOutcome
from aqp_ratelimit.strategies.base import IngestionRateLimitStrategy

logger = logging.getLogger(__name__)


_LUA_DIR = Path(__file__).resolve().parents[3] / "lua"


def _load_script(name: str) -> str:
    path = _LUA_DIR / name
    return path.read_text(encoding="utf-8")


class RedisTokenBucketStrategy(IngestionRateLimitStrategy):
    """Canonical Redis Lua token-bucket strategy."""

    strategy_kind = "redis_token_bucket"
    strategy_alias = "RedisTokenBucketStrategy"
    strategy_priority = 10  # lower is preferred; production default

    DEFAULT_CAPACITY: int = 60
    DEFAULT_REFILL_RATE: float = 1.0

    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        redis_url: str | None = None,
        capacity: int = DEFAULT_CAPACITY,
        refill_rate: float = DEFAULT_REFILL_RATE,
        eager: bool = False,
    ) -> None:
        # Defer the Redis connection until first use so importing
        # this module on a host without a reachable Redis (CI test
        # workers, offline laptops, fresh dev images) does not block.
        # ``eager=True`` opts into the historical behaviour for
        # production smoke checks.
        self._explicit_client = redis_client
        self._redis_url = redis_url
        self._default_capacity = int(capacity)
        self._default_refill_rate = float(refill_rate)
        self._client = None
        self._scripts: dict[str, Any] = {}
        if eager:
            self._ensure_initialised()

    def _ensure_initialised(self) -> None:
        if self._client is not None:
            return
        client = self._explicit_client or self._build_client(self._redis_url)
        # Sanity-ping with a short timeout; raise so the factory can
        # fall back to InMemoryStrategy rather than block the caller.
        try:
            client.ping()
        except Exception as exc:  # noqa: BLE001
            raise RateLimitError(f"redis ping failed: {exc}") from exc
        self._client = client
        self._scripts = self._register_scripts()

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
        self._ensure_initialised()
        capacity, refill_rate = self._resolve_policy(service, ctx)
        key = self._bucket_key(user_id, service, key_id)
        now_ms = int(time.time() * 1000)
        try:
            result = self._scripts["token_bucket"](
                keys=[key],
                args=[
                    capacity,
                    refill_rate,
                    1.0,  # refill_interval (informational)
                    now_ms,
                    n_tokens,
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis token_bucket lua eval failed: %s", exc)
            raise RateLimitError(f"redis backend failure: {exc}") from exc
        allow_flag, new_tokens, retry_after = result
        return Decision(
            allow=bool(int(allow_flag)),
            remaining=float(new_tokens),
            capacity=float(capacity),
            refill_rate=float(refill_rate),
            retry_after_ms=int(retry_after),
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
        self._ensure_initialised()
        capacity, refill_rate = self._resolve_policy(service, ctx)
        bucket_key = self._bucket_key(user_id, service, key_id)
        rsv_id = str(uuid.uuid4())
        rsv_key = f"aqp:rl:rsv:{rsv_id}"
        now_ms = int(time.time() * 1000)
        try:
            result = self._scripts["reserve"](
                keys=[bucket_key, rsv_key],
                args=[
                    capacity,
                    refill_rate,
                    now_ms,
                    n_tokens,
                    ttl_s,
                    rsv_id,
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis reserve lua eval failed: %s", exc)
            raise RateLimitError(f"redis backend failure: {exc}") from exc
        allow_flag, remaining, ttl_back = result
        allow = bool(int(allow_flag))
        return ReserveOutcome(
            allow=allow,
            reservation_id=rsv_id if allow else None,
            requested=n_tokens,
            remaining=float(remaining),
            capacity=float(capacity),
            ttl_s=int(ttl_back) if allow else ttl_s,
            service=service,
            key_id=key_id,
            user_id=user_id,
        )

    def release(self, *, reservation_id: str) -> None:
        try:
            self._ensure_initialised()
        except RateLimitError:
            return
        capacity = self._default_capacity
        rsv_key = f"aqp:rl:rsv:{reservation_id}"
        now_ms = int(time.time() * 1000)
        try:
            self._scripts["release"](
                keys=[rsv_key],
                args=[capacity, now_ms],
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("redis release lua eval failed for %s: %s", reservation_id, exc)

    def status(
        self,
        *,
        user_id: str,
        service: str,
        key_id: str,
    ) -> Decision:
        try:
            self._ensure_initialised()
        except RateLimitError:
            return Decision(
                allow=True,
                remaining=float(self._default_capacity),
                capacity=float(self._default_capacity),
                refill_rate=self._default_refill_rate,
                service=service,
                key_id=key_id,
                user_id=user_id,
            )
        key = self._bucket_key(user_id, service, key_id)
        try:
            raw = self._client.hmget(key, "tokens", "last_refill")
        except Exception as exc:  # noqa: BLE001
            logger.debug("status read failed: %s", exc)
            raw = (None, None)
        tokens_raw, last_refill_raw = raw if raw else (None, None)
        if tokens_raw is None:
            return Decision(
                allow=True,
                remaining=float(self._default_capacity),
                capacity=float(self._default_capacity),
                refill_rate=self._default_refill_rate,
                service=service,
                key_id=key_id,
                user_id=user_id,
            )
        tokens = float(tokens_raw)
        capacity = float(self._default_capacity)
        rate = self._default_refill_rate
        if last_refill_raw is not None:
            elapsed = max(
                0.0,
                (time.time() * 1000 - float(last_refill_raw)) / 1000.0,
            )
            tokens = min(capacity, tokens + elapsed * rate)
        return Decision(
            allow=tokens >= 1,
            remaining=tokens,
            capacity=capacity,
            refill_rate=rate,
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
    ) -> tuple[int, float]:
        if ctx is None:
            return self._default_capacity, self._default_refill_rate
        return (
            int(ctx.get("capacity", self._default_capacity)),
            float(ctx.get("refill_rate", self._default_refill_rate)),
        )

    def _build_client(self, url: str | None) -> Any:
        try:
            import redis
        except ImportError as exc:
            raise RateLimitError(
                "redis>=5.0 required for RedisTokenBucketStrategy"
            ) from exc
        try:
            from aqp.config import settings

            target = url or getattr(settings, "ratelimit_redis_url", None) or getattr(
                settings, "redis_url", "redis://localhost:6379/0"
            )
        except Exception:  # noqa: BLE001
            target = url or "redis://localhost:6379/0"
        # Short timeouts so a missing Redis surfaces as a fast
        # RateLimitError, not a 30s connect hang.
        return redis.from_url(
            target,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )

    def _register_scripts(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for short, filename in (
            ("token_bucket", "token_bucket.lua"),
            ("reserve", "reserve.lua"),
            ("release", "release.lua"),
        ):
            try:
                source = _load_script(filename)
                out[short] = self._client.register_script(source)
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not register lua script %s: %s", filename, exc)
        return out


__all__ = ["RedisTokenBucketStrategy"]
