"""gRPC adapter base.

Provides a thin wrapper around ``grpc.aio.Channel`` with TLS,
mutual-auth, and reconnect plumbing. Concrete venue adapters attach
generated client stubs and override :meth:`stream` / :meth:`place`
on the ``MarketDataAdapter`` / ``ExecutionAdapter`` ABCs.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GrpcAdapterError(RuntimeError):
    """Raised on terminal gRPC transport failure."""


class GrpcAdapterBase:
    """Reusable gRPC connection management.

    Concrete venue adapters call :meth:`connect_channel` during their
    :meth:`MarketDataAdapter.connect` / :meth:`ExecutionAdapter.connect`
    impl and attach generated stubs to ``self.channel``.
    """

    def __init__(
        self,
        *,
        target: str,
        use_tls: bool = True,
        max_message_length_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        self.target = target
        self.use_tls = use_tls
        self._max_msg_len = max_message_length_bytes
        self.channel: Any | None = None

    async def connect_channel(self, *, credentials: Any | None = None) -> None:
        try:
            import grpc  # type: ignore[import-not-found]
            from grpc import aio as _grpc_aio  # type: ignore[import-not-found]
        except ImportError as exc:
            raise GrpcAdapterError("grpcio required for GrpcAdapterBase") from exc

        options = [
            ("grpc.max_send_message_length", self._max_msg_len),
            ("grpc.max_receive_message_length", self._max_msg_len),
        ]
        if self.use_tls:
            creds = credentials or grpc.ssl_channel_credentials()
            self.channel = _grpc_aio.secure_channel(self.target, creds, options=options)
        else:
            self.channel = _grpc_aio.insecure_channel(self.target, options=options)
        logger.info("grpc channel opened: %s (tls=%s)", self.target, self.use_tls)

    async def aclose(self) -> None:
        if self.channel is not None:
            try:
                await self.channel.close(grace=5.0)  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
            self.channel = None


__all__ = ["GrpcAdapterBase", "GrpcAdapterError"]
