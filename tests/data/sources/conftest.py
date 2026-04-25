"""Shared fixtures for data-plane expansion tests.

Uses an in-memory SQLite DB with ``Base.metadata.create_all`` to give
each test a clean schema without touching Postgres. The ``get_session``
helper is monkeypatched globally via :mod:`aqp.persistence.db` so every
module that imports it shares the same engine.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aqp.persistence.models import Base


@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def sqlite_session_factory(sqlite_engine):
    return sessionmaker(bind=sqlite_engine, autocommit=False, autoflush=False, future=True)


@pytest.fixture
def patched_db(monkeypatch, sqlite_session_factory) -> Iterator[Any]:
    """Rewire ``get_session`` (in ``aqp.persistence.db``) to use SQLite."""

    @contextmanager
    def _get_session() -> Iterator[Any]:
        session = sqlite_session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # Rewire both the canonical path and everywhere it's already imported.
    monkeypatch.setattr("aqp.persistence.db.get_session", _get_session)
    monkeypatch.setattr("aqp.data.catalog.get_session", _get_session)
    monkeypatch.setattr(
        "aqp.data.sources.registry.get_session",
        _get_session,
    )
    monkeypatch.setattr(
        "aqp.data.sources.resolvers.identifiers.get_session",
        _get_session,
    )
    monkeypatch.setattr(
        "aqp.data.sources.fred.catalog.get_session",
        _get_session,
    )
    monkeypatch.setattr(
        "aqp.data.sources.sec.catalog.get_session",
        _get_session,
    )
    monkeypatch.setattr(
        "aqp.data.sources.gdelt.catalog.get_session",
        _get_session,
    )
    monkeypatch.setattr(
        "aqp.data.sources.gdelt.subject_filter.get_session",
        _get_session,
    )

    yield _get_session
