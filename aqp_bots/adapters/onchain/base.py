"""Generic EVM chain adapter built on web3.py.

For DEX backrun / arbitrage bots: subscribe to the pending-tx mempool
(via Blocknative, Alchemy WebSocket, or self-hosted node), simulate
candidate transactions, and route winners through
:class:`FlashbotsClient` (see ``flashbots.py``).
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)


class OnChainAdapterError(RuntimeError):
    """Raised on RPC failure."""


class OnChainAdapter:
    """Web3 JSON-RPC adapter for EVM chains.

    Concrete bots subclass to attach contract ABIs + DEX-specific
    routers. The base class provides:

    - ``connect()`` — opens a WS or HTTP web3 provider
    - ``stream_pending()`` — yields pending transactions
    - ``simulate()`` — calls ``eth_call`` for dry-run
    """

    def __init__(
        self,
        *,
        rpc_url: str,
        ws_url: str | None = None,
        chain_id: int = 1,
    ) -> None:
        self.rpc_url = rpc_url
        self.ws_url = ws_url
        self.chain_id = chain_id
        self._w3: Any | None = None
        self._ws_w3: Any | None = None

    async def connect(self) -> None:
        try:
            from web3 import AsyncHTTPProvider, AsyncWeb3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise OnChainAdapterError("web3 package required for OnChainAdapter") from exc

        self._w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        if self.ws_url:
            try:
                from web3 import WebsocketProviderV2  # type: ignore[import-not-found]

                self._ws_w3 = AsyncWeb3.persistent_websocket(WebsocketProviderV2(self.ws_url))
            except Exception:  # noqa: BLE001
                logger.debug("ws provider unavailable; continuing with HTTP only", exc_info=True)

    async def stream_pending(self) -> AsyncIterator[dict[str, Any]]:
        """Yield pending transactions from the mempool.

        Requires a WS provider; HTTP-only providers raise.
        """
        if self._ws_w3 is None:
            raise OnChainAdapterError(
                "stream_pending requires a WebSocket provider; pass ws_url=..."
            )
        async with self._ws_w3 as w3:  # type: ignore[union-attr]
            sub_id = await w3.eth.subscribe("newPendingTransactions")  # type: ignore[attr-defined]
            try:
                async for tx in w3.socket.process_subscriptions():
                    yield dict(tx)
            finally:
                await w3.eth.unsubscribe(sub_id)

    async def simulate_call(
        self,
        *,
        to: str,
        data: bytes,
        from_address: str | None = None,
        value: int = 0,
    ) -> bytes:
        """Dry-run a transaction via ``eth_call``."""
        if self._w3 is None:
            raise OnChainAdapterError("call connect() before simulate_call()")
        tx = {"to": to, "data": data, "value": value}
        if from_address:
            tx["from"] = from_address
        return await self._w3.eth.call(tx)  # type: ignore[union-attr]

    async def aclose(self) -> None:
        # web3.py providers don't expose explicit close; underlying httpx
        # client is reaped on GC. Nothing to do.
        pass


__all__ = ["OnChainAdapter", "OnChainAdapterError"]
