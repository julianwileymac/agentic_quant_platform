"""WebSocket surface for the admin BFF.

The single :class:`/admin/ws` endpoint multiplexes channels backed by
Redis Streams so multiple admin replicas can fan-out consistently.
"""
from __future__ import annotations

from aqp_admin.ws.gateway import router

__all__ = ["router"]
