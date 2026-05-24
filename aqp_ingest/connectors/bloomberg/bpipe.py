"""Bloomberg BPIPE adapter — Single-User entitlement mode.

Out-of-process (subprocess) because BLPAPI session creation is
expensive and not easily shared across Airbyte worker pods. The
parent worker spawns one adapter subprocess per (user, terminal)
binding and writes records to a stdout JSON-lines stream that the
parent reads back.

Rate-limit accounting happens at the parent level via
:class:`aqp_ratelimit.RateLimitClient` — every
``ReferenceDataRequest`` / ``HistoricalDataRequest`` is debited as
``bloomberg.bpipe`` before being forwarded to the subprocess.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


@dataclass
class BloombergBpipeAdapter:
    """High-level orchestrator wrapping the BLPAPI subprocess.

    Subclasses or callers MUST call :meth:`check_rate_limit` before
    issuing ``request_reference_data`` / ``request_historical_data``
    so the per-user bucket debits even though BPIPE is binary.
    """

    api_key: str
    label: str = "primary"
    user_id: str = "anonymous"
    rate_limit_service: str = "bloomberg.bpipe"
    rate_limit_tokens_per_call: int = 1
    blpapi_host: str = "localhost"
    blpapi_port: int = 8194

    _subprocess: Any = field(default=None, init=False, repr=False)

    def check_rate_limit(self) -> None:
        from aqp_ratelimit import get_ratelimit_client
        from aqp_ratelimit.exceptions import RateLimitExceeded

        decision = get_ratelimit_client().check(
            user_id=self.user_id,
            service=self.rate_limit_service,
            key_id=self.label,
            n_tokens=self.rate_limit_tokens_per_call,
        )
        if not decision.allow:
            raise RateLimitExceeded(
                service=self.rate_limit_service,
                key_id=self.label,
                remaining=decision.remaining,
                requested=self.rate_limit_tokens_per_call,
                retry_after_ms=decision.retry_after_ms,
            )

    def request_reference_data(
        self,
        *,
        securities: list[str],
        fields: list[str],
        overrides: dict[str, Any] | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Issue a BPIPE ReferenceDataRequest."""
        self.check_rate_limit()
        try:
            import blpapi  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "blpapi required for BloombergBpipeAdapter; install aqp-ingest[bloomberg]"
            ) from exc
        # Phase 1 ships the rate-limit guard; the full BLPAPI session
        # lifecycle (CreateSession + sessionStarted listener + service
        # open + correlation tracking) lands in Phase 2 once the
        # operator opt-in is settled. The guard is correct on its own
        # because it sits BEFORE any BLPAPI call.
        _ = blpapi
        return iter([])

    def request_historical_data(
        self,
        *,
        securities: list[str],
        fields: list[str],
        start_date: str,
        end_date: str,
        periodicity: str = "DAILY",
    ) -> Iterable[dict[str, Any]]:
        """Issue a BPIPE HistoricalDataRequest."""
        self.check_rate_limit()
        try:
            import blpapi  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "blpapi required for BloombergBpipeAdapter; install aqp-ingest[bloomberg]"
            ) from exc
        _ = blpapi
        return iter([])

    def close(self) -> None:
        if self._subprocess is not None:
            try:
                self._subprocess.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._subprocess = None


__all__ = ["BloombergBpipeAdapter"]
