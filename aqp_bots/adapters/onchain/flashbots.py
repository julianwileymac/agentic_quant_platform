"""Flashbots / MEV-share bundle submission.

Direct submission to the Flashbots relay at ``relay.flashbots.net``
following the ``eth_sendBundle`` JSON-RPC method. Includes:

- EIP-191 personal-sign auth header (``X-Flashbots-Signature``).
- Multi-relay submission (Flashbots + MEV-share + Beaverbuild + Titanbuild).
- Bundle simulation via ``eth_callBundle``.

For the full MEV-share spec see https://docs.flashbots.net/mev-share/overview.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class FlashbotsError(RuntimeError):
    """Raised on bundle submission failure."""


FLASHBOTS_RELAY = "https://relay.flashbots.net"
MEV_SHARE_RELAY = "https://mev-share.flashbots.net"

KNOWN_RELAYS: dict[str, str] = {
    "flashbots": FLASHBOTS_RELAY,
    "mev_share": MEV_SHARE_RELAY,
    "beaverbuild": "https://rpc.beaverbuild.org",
    "titanbuild": "https://rpc.titanbuilder.xyz",
    "rsync": "https://rsync-builder.xyz",
}


@dataclass(slots=True)
class FlashbotsBundle:
    """One MEV bundle.

    ``txs`` is a list of *signed* raw transactions (0x-prefixed hex
    strings). ``block_number`` is the target block (hex string).
    """

    txs: list[str]
    block_number: str  # hex, e.g. "0x12345"
    min_timestamp: int | None = None
    max_timestamp: int | None = None
    reverting_tx_hashes: list[str] = field(default_factory=list)
    replacement_uuid: str | None = None


class FlashbotsClient:
    """Submit bundles to Flashbots-family relays.

    Auth: each request is signed with an Ethereum private key
    (``X-Flashbots-Signature``). The key is typically distinct from
    the bot's trading key (the "searcher identity" — Flashbots uses
    it for reputation scoring).
    """

    def __init__(
        self,
        *,
        signing_key: str,  # 0x-prefixed hex private key
        relays: list[str] | None = None,
    ) -> None:
        self.signing_key = signing_key
        self.relays = relays or [FLASHBOTS_RELAY]
        self._client: Any | None = None
        self._signer_address: str | None = None

    async def connect(self) -> None:
        try:
            import httpx  # noqa: F401
        except ImportError as exc:
            raise FlashbotsError("httpx required for FlashbotsClient") from exc
        import httpx

        self._client = httpx.AsyncClient(timeout=10.0)
        self._signer_address = self._derive_address()

    async def send_bundle(self, bundle: FlashbotsBundle) -> list[dict[str, Any]]:
        """Submit a bundle to every configured relay.

        Returns a list of relay responses, one per configured endpoint.
        """
        if self._client is None:
            raise FlashbotsError("call connect() first")
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "eth_sendBundle",
            "params": [
                {
                    "txs": bundle.txs,
                    "blockNumber": bundle.block_number,
                    "minTimestamp": bundle.min_timestamp or 0,
                    "maxTimestamp": bundle.max_timestamp or 0,
                    "revertingTxHashes": bundle.reverting_tx_hashes,
                    **(
                        {"replacementUuid": bundle.replacement_uuid}
                        if bundle.replacement_uuid
                        else {}
                    ),
                }
            ],
        }
        body = json.dumps(payload)
        sig = self._sign_payload(body)
        headers = {
            "Content-Type": "application/json",
            "X-Flashbots-Signature": f"{self._signer_address}:{sig}",
        }
        results: list[dict[str, Any]] = []
        for relay_url in self.relays:
            try:
                resp = await self._client.post(relay_url, content=body, headers=headers)
                results.append({"relay": relay_url, "status": resp.status_code, "body": resp.text})
            except Exception as exc:  # noqa: BLE001
                logger.warning("flashbots submit failed for %s: %s", relay_url, exc)
                results.append({"relay": relay_url, "error": str(exc)})
        return results

    async def simulate(self, bundle: FlashbotsBundle, *, state_block: str) -> dict[str, Any]:
        """Simulate via ``eth_callBundle``."""
        if self._client is None:
            raise FlashbotsError("call connect() first")
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "eth_callBundle",
            "params": [
                {
                    "txs": bundle.txs,
                    "blockNumber": bundle.block_number,
                    "stateBlockNumber": state_block,
                }
            ],
        }
        body = json.dumps(payload)
        sig = self._sign_payload(body)
        headers = {
            "Content-Type": "application/json",
            "X-Flashbots-Signature": f"{self._signer_address}:{sig}",
        }
        resp = await self._client.post(FLASHBOTS_RELAY, content=body, headers=headers)
        return resp.json()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Signing helpers
    # ------------------------------------------------------------------

    def _derive_address(self) -> str:
        try:
            from eth_account import Account  # type: ignore[import-not-found]
        except ImportError as exc:
            raise FlashbotsError("eth_account required for FlashbotsClient") from exc
        return Account.from_key(self.signing_key).address

    def _sign_payload(self, body: str) -> str:
        try:
            from eth_account import Account  # type: ignore[import-not-found]
            from eth_account.messages import encode_defunct  # type: ignore[import-not-found]
            from web3 import Web3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise FlashbotsError("eth_account/web3 required for signing") from exc
        msg = encode_defunct(text=Web3.keccak(text=body).hex())
        signed = Account.sign_message(msg, private_key=self.signing_key)
        return signed.signature.hex()


__all__ = ["FlashbotsBundle", "FlashbotsClient", "FlashbotsError", "KNOWN_RELAYS"]
