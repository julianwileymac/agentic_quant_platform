"""RFC 8594 Deprecation + Sunset HTTP headers for the public API.

Phase 6 of the docs-migration plan. AQP uses Stripe-style date-epoch
versioning. When an endpoint or response shape is deprecated, the
backend MUST emit the RFC 8594 ``Deprecation`` and ``Sunset``
headers so consumers can plan their migration.

Usage::

    from aqp.api.deprecation import deprecate

    @router.get("/strategies/legacy")
    @deprecate(
        sunset_at=date(2027, 6, 1),
        replacement="/strategies",
        guide="https://docs.aqp.fund/release-notes/2026-06-01-initial-release",
    )
    def list_legacy_strategies(...) -> ...: ...

The decorator stamps the response with the headers documented in
RFC 8594 §2 and §3 and adds a ``Link`` header pointing at the
sunset documentation (per RFC 8288).

Hard rules respected:

- ``aqp-management-engine`` always-on (credential safety): the
  ``deprecation_documentation`` URL is public — never embed a token
  or secret material in the value.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from functools import wraps
from typing import Any, Callable, TypeVar

from email.utils import format_datetime
from fastapi import Response

logger = logging.getLogger(__name__)


F = TypeVar("F", bound=Callable[..., Any])


def _http_date(d: date | datetime) -> str:
    """Format a date / datetime as RFC 7231 IMF-fixdate."""
    if isinstance(d, datetime):
        dt = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    else:
        dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return format_datetime(dt, usegmt=True)


def deprecate(
    *,
    sunset_at: date | datetime,
    replacement: str | None = None,
    guide: str | None = None,
    deprecation_at: date | datetime | None = None,
) -> Callable[[F], F]:
    """Return a decorator that stamps RFC 8594 + RFC 8288 headers.

    Args:
        sunset_at: When the endpoint will return ``410 Gone``.
        replacement: Optional URL of the replacement endpoint.
        guide: Optional URL of the migration documentation.
        deprecation_at: Optional timestamp of when the deprecation
            began. Defaults to the function-decoration time, which
            is the deploy timestamp in practice.
    """
    if deprecation_at is None:
        deprecation_at = datetime.now(timezone.utc)

    def _decorator(fn: F) -> F:
        @wraps(fn)
        async def _wrapper(*args: Any, response: Response | None = None, **kwargs: Any) -> Any:
            # Find the Response dep — FastAPI injects one when the
            # function signature includes `response: Response`.
            target_response = response
            if target_response is None:
                # Inspect args for a Response (when used outside FastAPI).
                for candidate in args:
                    if isinstance(candidate, Response):
                        target_response = candidate
                        break
            if target_response is not None:
                target_response.headers["Deprecation"] = _http_date(deprecation_at)
                target_response.headers["Sunset"] = _http_date(sunset_at)
                links: list[str] = []
                if replacement:
                    links.append(f'<{replacement}>; rel="successor-version"')
                if guide:
                    links.append(f'<{guide}>; rel="deprecation"; type="text/html"')
                if links:
                    target_response.headers["Link"] = ", ".join(links)
            return await fn(*args, response=response, **kwargs) if response else await fn(*args, **kwargs)

        return _wrapper  # type: ignore[return-value]

    return _decorator


__all__ = ["deprecate", "_http_date"]
