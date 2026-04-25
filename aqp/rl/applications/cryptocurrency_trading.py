"""Cryptocurrency trading façade (placeholder).

FinRL ships dedicated crypto envs that rely on a separate data source
(Binance / CCXT). This module hosts the integration point so the API
surface is stable; the actual env will land once the crypto data
adapter is merged.

Until then :func:`train_crypto_trading` raises ``NotImplementedError``
with a clear next-step pointer.
"""
from __future__ import annotations

from typing import Any


def train_crypto_trading(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError(
        "Cryptocurrency trading requires a crypto data adapter "
        "(Binance / CCXT). See `aqp/data/ingestion.py` to plug one in "
        "and then reuse `aqp.rl.applications.stock_trading.train_stock_trading` "
        "with the crypto symbols."
    )
