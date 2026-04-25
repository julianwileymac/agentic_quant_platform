"""Shared FastAPI dependencies."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from aqp.persistence.db import async_session_dep


async def db() -> AsyncGenerator[AsyncSession, None]:
    async for s in async_session_dep():
        yield s
