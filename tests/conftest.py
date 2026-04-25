"""Shared pytest fixtures — synthetic bars + optional in-memory DB."""
from __future__ import annotations

from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests hermetic: never emit real OTel spans.

    We deliberately do NOT rebind ``aqp.config.settings`` here because
    downstream modules capture the singleton via ``from aqp.config import
    settings`` at import time, and swapping the reference breaks tests
    that ``monkeypatch.setattr(cfg.settings, ...)``.
    """
    monkeypatch.setenv("AQP_OTEL_ENDPOINT", "")
    try:
        from aqp.observability import tracing as _tracing

        _tracing._tracer_provider = None
        _tracing._instrumented.clear()
    except Exception:
        pass


@pytest.fixture
def in_memory_db(monkeypatch: pytest.MonkeyPatch):
    """Spin up an in-memory SQLite session and patch ``get_session`` to use it.

    Creates every table SQLAlchemy knows about so deep persistence tests
    (entities API, portfolio service, feature sets) can run without
    Postgres. Each invocation gets a fresh DB so tests are isolated.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Force-import every model module so ``Base.metadata`` is fully populated.
    from aqp.persistence import (  # noqa: F401
        models,
        models_entities,
    )
    try:
        from aqp.persistence import (  # noqa: F401
            models_events,
            models_fundamentals,
            models_instruments,
            models_macro,
            models_news,
            models_ownership,
            models_taxonomy,
        )
    except Exception:
        pass
    from aqp.persistence.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

    @contextmanager
    def _patched_get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    from aqp.persistence import db as _db_mod

    monkeypatch.setattr(_db_mod, "get_session", _patched_get_session)
    # Also patch any module that already imported get_session at module scope.
    for module_name in (
        "aqp.api.routes.entities",
        "aqp.services.portfolio_service",
        "aqp.data.feature_sets",
    ):
        try:
            import importlib

            mod = importlib.import_module(module_name)
            monkeypatch.setattr(mod, "get_session", _patched_get_session, raising=False)
        except Exception:
            pass
    return Session


@pytest.fixture(scope="session")
def synthetic_bars() -> pd.DataFrame:
    """Three-year synthetic OHLCV for 5 tickers. Deterministic."""
    rng = np.random.default_rng(42)
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE"]
    dates = pd.bdate_range("2021-01-01", "2023-12-29")
    frames = []
    for t in tickers:
        returns = rng.normal(0.0005, 0.015, size=len(dates))
        prices = 100 * (1 + pd.Series(returns)).cumprod().values
        high = prices * (1 + rng.uniform(0, 0.01, len(dates)))
        low = prices * (1 - rng.uniform(0, 0.01, len(dates)))
        opens = low + rng.uniform(0, 1, len(dates)) * (high - low)
        volume = rng.integers(1_000_000, 10_000_000, len(dates)).astype(float)
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": dates,
                    "vt_symbol": f"{t}.NASDAQ",
                    "open": opens,
                    "high": high,
                    "low": low,
                    "close": prices,
                    "volume": volume,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)
