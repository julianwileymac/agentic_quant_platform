"""On-chain venue adapter family.

Two layers:

- :class:`OnChainAdapter` — generic ``web3.py`` JSON-RPC adapter for any
  EVM chain (Ethereum L1, Arbitrum, Base, Polygon, …).
- :class:`FlashbotsClient` — submits bundles to the Flashbots relay at
  ``relay.flashbots.net`` (and MEV-share at ``mev-share.flashbots.net``).
"""
from __future__ import annotations

from aqp_bots.adapters.onchain.base import OnChainAdapter, OnChainAdapterError
from aqp_bots.adapters.onchain.flashbots import (
    FlashbotsBundle,
    FlashbotsClient,
    FlashbotsError,
)

__all__ = [
    "FlashbotsBundle",
    "FlashbotsClient",
    "FlashbotsError",
    "OnChainAdapter",
    "OnChainAdapterError",
]
