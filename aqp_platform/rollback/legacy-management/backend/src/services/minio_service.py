"""
MinIO integration service.

Provides health checks for the MinIO API endpoint.
"""

import logging
from typing import Optional

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)


class MinioService:
    """Service for MinIO health checks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.minio.endpoint.rstrip("/")
        self.health_path = settings.minio.health_path
        self.timeout = settings.minio.timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def health_check(self) -> bool:
        if not self.settings.minio.enabled:
            return False

        try:
            response = await self.client.get(self.health_path)
            return response.status_code == 200
        except Exception as exc:  # noqa: BLE001
            logger.error("MinIO health check failed: %s", exc)
            return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
