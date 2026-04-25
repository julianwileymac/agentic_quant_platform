"""SEC EDGAR adapter (powered by edgartools).

Install the optional extra to enable:

    pip install "agentic-quant-platform[sec]"

Set ``AQP_SEC_EDGAR_IDENTITY="Your Name your@email.com"`` in the
environment (edgartools requires it) before using the adapter.
"""
from __future__ import annotations

from aqp.data.sources.sec.client import SecClient, SecClientError
from aqp.data.sources.sec.filings import SecFilingsAdapter

__all__ = ["SecClient", "SecClientError", "SecFilingsAdapter"]
