"""Market-data ingesters: IBKR + Alpaca -> Kafka."""
from __future__ import annotations

from aqp.streaming.ingesters.base import BaseIngester, IngesterMetrics

__all__ = ["BaseIngester", "IngesterMetrics"]
