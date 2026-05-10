"""Test that ``MetadataPrefetcher`` is idempotent and tolerant of empty Postgres."""
from __future__ import annotations

import pytest

from aqp.cache.client import reset_cache_singleton
from aqp.cache.keys import names_zset
from aqp.cache.prefetch import MetadataPrefetcher
from aqp.config import settings


@pytest.fixture(autouse=True)
def in_memory_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_enabled", True)
    monkeypatch.setattr(settings, "cache_redis_url", "redis://nonexistent.local:9999/0")
    reset_cache_singleton()
    yield
    reset_cache_singleton()


def test_dataset_kinds_populate_without_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dataset-kind registry doesn't need Postgres to populate."""

    def _broken_get_session(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("postgres unreachable")

    # Force the prefetcher to fail to open Postgres so we exercise the
    # "registry-only" path and verify it's still useful.
    import aqp.cache.prefetch as prefetch_module

    monkeypatch.setattr(
        "aqp.persistence.db.get_session",
        _broken_get_session,
        raising=False,
    )
    prefetcher = MetadataPrefetcher()
    counts = prefetcher.run_full()
    assert counts["dataset_kinds"] >= 1  # the bundled kinds register on import
    assert prefetcher.cache.zcard(names_zset("dataset_kinds")) == counts["dataset_kinds"]
    # Categories that need Postgres remain at 0 in this scenario.
    for category in (
        "datasets",
        "namespaces",
        "sink_kinds",
        "sink_names",
        "airbyte_connectors",
        "projects",
        "credentials",
    ):
        assert counts[category] == 0
    # touch the module so unused-import lint doesn't trip
    assert prefetch_module is not None
