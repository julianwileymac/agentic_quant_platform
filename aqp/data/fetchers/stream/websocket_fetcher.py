"""WebSocket micro-batch fetcher (preview).

Connects to ``url``, optionally sends a subscribe payload, then reads
messages until ``max_messages`` or ``timeout_seconds``. Each parsed
JSON message becomes a row.

Useful for sandboxing IBKR / Polygon / Alpaca-style streams in a
preview window without wiring an entire long-running ingester.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    register_source_fetcher,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.websocket",
    display_name="WebSocket Stream (preview)",
    kind=FetcherKind.STREAM,
    description="Connect to a WebSocket, consume a bounded burst, return Arrow rows.",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("stream.websocket",),
)
class WebSocketFetcher(Fetcher):
    """Consume a bounded burst from a WebSocket endpoint."""

    def __init__(
        self,
        *,
        url: str,
        subscribe_payload: dict[str, Any] | None = None,
        max_messages: int = 200,
        timeout_seconds: float = 30.0,
        chunk_rows: int = 200,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.url = url
        self.subscribe_payload = subscribe_payload
        self.max_messages = max(1, int(max_messages))
        self.timeout_seconds = float(timeout_seconds)
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return self.url

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            from websockets.sync.client import connect
        except Exception as exc:  # noqa: BLE001 - optional dep
            raise RuntimeError(
                f"WebSocketFetcher requires websockets: {exc}"
            ) from exc

        rows: list[dict[str, Any]] = []
        consumed = 0
        with connect(self.url, open_timeout=self.timeout_seconds) as ws:
            if self.subscribe_payload is not None:
                ws.send(json.dumps(self.subscribe_payload))
            ws_timeout = self.timeout_seconds
            while consumed < self.max_messages:
                try:
                    msg = ws.recv(timeout=ws_timeout)
                except TimeoutError:
                    break
                except Exception as exc:  # noqa: BLE001
                    logger.debug("websocket recv terminated: %s", exc)
                    break
                if isinstance(msg, (bytes, bytearray)):
                    try:
                        msg = msg.decode("utf-8")
                    except Exception:  # noqa: BLE001
                        msg = ""
                try:
                    body = json.loads(msg) if msg else {}
                    if not isinstance(body, dict):
                        body = {"__value": body}
                except Exception:  # noqa: BLE001
                    body = {"__value": msg}
                rows.append(body)
                consumed += 1
                if len(rows) >= self.chunk_rows:
                    yield from self._to_batches(rows)
                    rows = []
        if rows:
            yield from self._to_batches(rows)

    @staticmethod
    def _to_batches(rows: list[dict[str, Any]]) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        if not rows:
            return
        table = pa.Table.from_pylist(rows)
        yield from table.to_batches()
