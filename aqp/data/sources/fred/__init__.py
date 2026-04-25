"""FRED (Federal Reserve Economic Data) adapter.

Wraps the free FRED REST API (https://fred.stlouisfed.org/docs/api/fred/)
with retry, rate-limit awareness and catalog/identifier emission. The
vendor library ``fredapi`` is an optional dependency installed via the
``fred`` extra; when it's missing, the adapter falls back to raw httpx
calls so the base install keeps working.
"""
from __future__ import annotations

from aqp.data.sources.fred.client import FredClient, FredClientError
from aqp.data.sources.fred.series import FredSeriesAdapter

__all__ = ["FredClient", "FredClientError", "FredSeriesAdapter"]
