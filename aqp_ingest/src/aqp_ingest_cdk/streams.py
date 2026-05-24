"""RateLimitedHttpStream — Airbyte CDK HttpStream with per-user buckets.

The stock Airbyte CDK only reacts to 429s after the fact (per docs.
airbyte.com/platform/connector-development/cdk-python/http-streams:
"It is not currently possible to specify a rate limit Airbyte
should adhere to when making requests"). This subclass calls the
canonical :class:`aqp_ratelimit.RateLimitClient` BEFORE every
outbound request so the (user_id, service, key_id) bucket debits
preemptively and the connector never burns budget on retries.

When ``aqp_ratelimit.exceptions.RateLimitExceeded`` is raised the
stream surfaces an Airbyte ``UserDefinedBackoffException`` with the
correct ``backoff_seconds`` so the worker waits before re-attempting.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


try:
    from airbyte_cdk.sources.streams.http import HttpStream
    from airbyte_cdk.sources.streams.http.exceptions import (
        UserDefinedBackoffException,
    )
except ImportError:  # pragma: no cover — optional dep
    HttpStream = object  # type: ignore[misc,assignment]

    class UserDefinedBackoffException(Exception):  # type: ignore[no-redef]
        def __init__(self, backoff: float, request: Any = None, response: Any = None):
            self.backoff = backoff
            self.request = request
            self.response = response
            super().__init__(f"backoff for {backoff}s")


class RateLimitedHttpStream(HttpStream):
    """Airbyte CDK :class:`HttpStream` with preemptive per-bucket rate limiting.

    Subclasses set:

    - :attr:`rate_limit_service` — the canonical service descriptor
      string used as the second element of the
      (user_id, service, key_id) 3-tuple. Mirrors the ``service``
      column on :class:`aqp.persistence.models_ratelimit.RateLimitPolicy`.
      Examples: ``"polygon.aggregates"``, ``"databento.historical"``.
    - :attr:`rate_limit_key_id` — the per-user key label. The connector's
      user-facing config carries it; defaults to ``"primary"``.
    - :attr:`rate_limit_tokens_per_call` — tokens this stream debits
      per HTTP request. Defaults to 1; expensive endpoints can
      override.

    The stream resolves ``user_id`` from
    ``self.config['_aqp_owner_user_id']`` which the connector wraps
    set when the Airbyte sync job starts.
    """

    rate_limit_service: str = ""
    rate_limit_key_id: str = "primary"
    rate_limit_tokens_per_call: int = 1

    def _resolve_identity(self) -> tuple[str, str, str]:
        """Return the (user_id, service, key_id) for the bucket lookup."""
        cfg = getattr(self, "config", {}) or {}
        user_id = str(cfg.get("_aqp_owner_user_id", "anonymous"))
        service = (
            getattr(self, "rate_limit_service", "")
            or str(cfg.get("_aqp_rate_limit_service", ""))
        )
        key_id = (
            getattr(self, "rate_limit_key_id", "primary")
            or str(cfg.get("_aqp_rate_limit_key_id", "primary"))
        )
        if not service:
            service = self.__class__.__name__.lower()
        return user_id, service, key_id

    def _send_request(self, request, request_kwargs):  # type: ignore[override]
        from aqp_ratelimit import get_ratelimit_client
        from aqp_ratelimit.exceptions import RateLimitError

        user_id, service, key_id = self._resolve_identity()
        n = int(getattr(self, "rate_limit_tokens_per_call", 1))
        client = get_ratelimit_client()
        try:
            decision = client.check(
                user_id=user_id,
                service=service,
                key_id=key_id,
                n_tokens=n,
            )
        except RateLimitError as exc:
            logger.warning(
                "rate-limit backend failure on %s/%s: %s; allowing through",
                service,
                key_id,
                exc,
            )
            return super()._send_request(request, request_kwargs)  # type: ignore[misc]
        if not decision.allow:
            backoff_s = max(0.5, decision.retry_after_ms / 1000.0)
            logger.info(
                "rate-limited %s/%s for user=%s, backing off %.1fs",
                service,
                key_id,
                user_id,
                backoff_s,
            )
            raise UserDefinedBackoffException(backoff=backoff_s, request=request)
        return super()._send_request(request, request_kwargs)  # type: ignore[misc]

    def should_retry(self, response) -> bool:  # type: ignore[override]
        """Honour vendor 429s on top of the preemptive bucket."""
        try:
            if response is not None and getattr(response, "status_code", 0) == 429:
                return True
        except Exception:  # noqa: BLE001
            pass
        try:
            return super().should_retry(response)  # type: ignore[misc]
        except Exception:  # noqa: BLE001
            return False

    def backoff_time(self, response) -> float | None:  # type: ignore[override]
        """Surface ``Retry-After`` when the vendor sets it."""
        if response is None:
            return None
        try:
            retry = response.headers.get("Retry-After")
            if retry is not None:
                return float(retry)
        except Exception:  # noqa: BLE001
            pass
        try:
            return super().backoff_time(response)  # type: ignore[misc]
        except Exception:  # noqa: BLE001
            return None


__all__ = ["RateLimitedHttpStream", "UserDefinedBackoffException"]
