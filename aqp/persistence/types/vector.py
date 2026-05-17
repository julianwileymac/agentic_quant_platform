"""SQLAlchemy ``Vector`` column type.

Wraps :class:`pgvector.sqlalchemy.Vector` when ``pgvector`` is
installed and falls back to a JSON-encoded ARRAY column on dialects
that don't ship the extension (used by the SQLite-backed test suite
so the ORM definitions stay importable).

The helper centralises the optional-import dance so model files only
need to do ``from aqp.persistence.types import Vector``.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def Vector(dim: int) -> Any:
    """Return a SQLAlchemy column type representing a ``vector(N)``.

    Resolution order:

    1. ``pgvector.sqlalchemy.Vector`` when the package is installed
       (production / pgvector image).
    2. ``sqlalchemy.dialects.postgresql.ARRAY(Float)`` when only
       SQLAlchemy is available (still gives us a usable column on
       postgres without the extension; reads/writes will round-trip
       as a Python list).
    3. ``sqlalchemy.JSON`` as the universal fallback for SQLite +
       MySQL test environments.
    """
    try:
        from pgvector.sqlalchemy import Vector as _PgVector  # type: ignore

        return _PgVector(int(dim))
    except Exception:  # noqa: BLE001 - pgvector is optional
        try:
            import sqlalchemy as sa
            from sqlalchemy.dialects.postgresql import ARRAY

            return ARRAY(sa.Float())
        except Exception:  # noqa: BLE001
            import sqlalchemy as sa

            return sa.JSON()


__all__ = ["Vector"]
