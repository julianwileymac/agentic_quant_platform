"""FastAPI WebSocket connection manager."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks WebSocket clients per task_id and fan-outs pub/sub messages."""

    def __init__(self) -> None:
        self._clients: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients[task_id].add(ws)

    async def disconnect(self, task_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._clients[task_id].discard(ws)
            if not self._clients[task_id]:
                self._clients.pop(task_id, None)

    async def broadcast(self, task_id: str, payload: dict[str, Any]) -> None:
        clients = list(self._clients.get(task_id, ()))
        for c in clients:
            try:
                await c.send_json(payload)
            except Exception:
                await self.disconnect(task_id, c)


manager = ConnectionManager()
