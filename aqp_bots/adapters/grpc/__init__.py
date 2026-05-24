"""gRPC adapter base.

Most institutional venues (CME, Eurex, ICE) provide gRPC alternatives
to FIX. This module ships the connection + auth + reconnect plumbing;
venue-specific adapters subclass to attach generated stubs.
"""
from __future__ import annotations

from aqp_bots.adapters.grpc.base import GrpcAdapterBase, GrpcAdapterError

__all__ = ["GrpcAdapterBase", "GrpcAdapterError"]
