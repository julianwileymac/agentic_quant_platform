from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import math

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aqp.persistence import Base
from aqp.persistence.models_instrument_catalog import InstrumentCatalog
from aqp.tasks import instrument_catalog_tasks as instrument_catalog_tasks_mod
from aqp.tasks.instrument_catalog_tasks import sync_finance_database

pytest.importorskip("celery")


@pytest.fixture
def sqlite_session_factory(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    @contextmanager
    def _patched_get_session():
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr("aqp.persistence.db.get_session", _patched_get_session)
    monkeypatch.setattr("aqp.tasks.instrument_catalog_tasks.get_session", _patched_get_session)
    monkeypatch.setattr("aqp.data.catalog.lineage.get_session", _patched_get_session)
    return SessionLocal


def test_row_dict_for_hash_excludes_volatile_fields() -> None:
    row = {
        "id": "abc",
        "universal_ticker": "AAPL",
        "exchange_code": "NASDAQ",
        "asset_class": "equity",
        "metadata_blob": {"name": "Apple"},
        "content_hash": "hash",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_catalog_sync": datetime.utcnow(),
    }
    payload = instrument_catalog_tasks_mod._row_dict_for_hash(row)
    assert "id" not in payload
    assert "content_hash" not in payload
    assert "created_at" not in payload
    assert "updated_at" not in payload
    assert "last_catalog_sync" not in payload
    assert payload["universal_ticker"] == "AAPL"


def test_scrub_nan_replaces_non_finite_values() -> None:
    payload = {
        "a": math.nan,
        "b": math.inf,
        "c": [1.0, -math.inf],
        "d": {"x": math.nan},
    }
    scrubbed = instrument_catalog_tasks_mod._scrub_nan(payload)
    assert scrubbed["a"] is None
    assert scrubbed["b"] is None
    assert scrubbed["c"][1] is None
    assert scrubbed["d"]["x"] is None


def test_sync_finance_database_skips_unchanged_rows(
    sqlite_session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fd = pytest.importorskip("financedatabase")

    class _StubAsset:
        def __init__(self, frame: pd.DataFrame) -> None:
            self._frame = frame

        def select(self) -> pd.DataFrame:
            return self._frame.copy()

    frames = {
        "Equities": pd.DataFrame([{"symbol": "EQ1", "exchange": "NASDAQ", "name": "Eq One"}]),
        "ETFs": pd.DataFrame([{"symbol": "ETF1", "exchange": "NYSE", "name": "Etf One"}]),
        "Funds": pd.DataFrame([{"symbol": "FUND1", "exchange": "NYSE", "name": "Fund One"}]),
        "Indices": pd.DataFrame([{"symbol": "IDX1", "exchange": "CBOE", "name": "Index One"}]),
        "Cryptos": pd.DataFrame([{"symbol": "BTC", "exchange": None, "name": "Bitcoin"}]),
        "Currencies": pd.DataFrame([{"symbol": "USD", "exchange": None, "name": "US Dollar"}]),
        "Moneymarkets": pd.DataFrame(
            [{"symbol": "MM1", "exchange": None, "name": "Money Market One"}]
        ),
    }

    for class_name, frame in frames.items():
        monkeypatch.setattr(fd, class_name, lambda frame=frame: _StubAsset(frame))

    first = sync_finance_database.run(batch_size=2)
    assert first["upserted"] > 0
    first_count: int
    with sqlite_session_factory() as session:
        first_count = session.query(InstrumentCatalog).count()
        assert first_count > 0

    second = sync_finance_database.run(batch_size=2)
    assert second["skipped"] > 0
    with sqlite_session_factory() as session:
        second_count = session.query(InstrumentCatalog).count()
        assert second_count == first_count
