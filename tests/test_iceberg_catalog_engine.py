"""Engine-level tests for :mod:`aqp.data.iceberg_catalog`.

These cover the new operational surface that lets callers tell "Iceberg is
down" from "table doesn't exist", and the bounded helpers that replace the
old full-table dedup scans in the intraday backfill loader.
"""
from __future__ import annotations

import importlib

import pytest

pyiceberg = pytest.importorskip("pyiceberg")
pa = pytest.importorskip("pyarrow")


@pytest.fixture
def fresh_catalog(tmp_path, monkeypatch):
    from aqp.config import settings as _settings
    from aqp.data import iceberg_catalog

    monkeypatch.setattr(_settings, "iceberg_warehouse", tmp_path, raising=False)
    monkeypatch.setattr(_settings, "iceberg_rest_uri", "", raising=False)
    monkeypatch.setattr(_settings, "iceberg_catalog_name", "aqp", raising=False)
    monkeypatch.setattr(_settings, "iceberg_namespace_default", "aqp", raising=False)
    importlib.reload(iceberg_catalog)
    iceberg_catalog.reset_catalog_cache()
    yield iceberg_catalog
    iceberg_catalog.reset_catalog_cache()


def _seed_table(catalog, identifier, rows):
    arrow = pa.table(rows)
    catalog.create_or_replace_table(identifier, arrow.schema)
    return catalog.append_arrow(identifier, arrow, create_if_missing=False)


def test_health_check_reports_ok_for_fresh_catalog(fresh_catalog):
    fresh_catalog.ensure_namespace("aqp")
    status = fresh_catalog.health_check()
    assert status["ok"] is True
    assert status["type"] == "sql"
    assert status["error"] is None
    assert status["namespace_count"] >= 1
    assert status["elapsed_seconds"] >= 0.0


def test_build_properties_includes_polaris_rest_credentials(monkeypatch):
    from aqp.config import settings as _settings
    from aqp.data import iceberg_catalog

    monkeypatch.setattr(_settings, "iceberg_rest_uri", "http://polaris:8181/api/catalog", raising=False)
    monkeypatch.setattr(_settings, "iceberg_s3_warehouse", "quickstart_catalog", raising=False)
    monkeypatch.setattr(_settings, "iceberg_rest_credential", "root:s3cr3t", raising=False)
    monkeypatch.setattr(_settings, "iceberg_rest_token", "", raising=False)
    monkeypatch.setattr(_settings, "iceberg_rest_oauth2_server_uri", "", raising=False)
    monkeypatch.setattr(_settings, "iceberg_rest_scope", "PRINCIPAL_ROLE:ALL", raising=False)
    monkeypatch.setattr(
        _settings,
        "iceberg_rest_extra_properties_json",
        '{"header.Polaris-Realm": "POLARIS"}',
        raising=False,
    )

    props = iceberg_catalog._build_properties()

    assert props["type"] == "rest"
    assert props["uri"] == "http://polaris:8181/api/catalog"
    assert props["warehouse"] == "quickstart_catalog"
    assert props["credential"] == "root:s3cr3t"
    assert props["scope"] == "PRINCIPAL_ROLE:ALL"
    assert props["header.Polaris-Realm"] == "POLARIS"


def test_health_check_returns_error_when_pyiceberg_load_fails(fresh_catalog, monkeypatch):
    def boom():
        raise RuntimeError("simulated catalog failure")

    monkeypatch.setattr(fresh_catalog, "get_catalog", boom)
    status = fresh_catalog.health_check(timeout=1.0)
    assert status["ok"] is False
    assert "simulated catalog failure" in status["error"]
    assert status["type"] == "sql"


def test_missing_rest_warehouse_lists_as_empty(fresh_catalog, monkeypatch):
    class MissingWarehouseCatalog:
        def list_namespaces(self):
            raise RuntimeError("NotFoundException: Unable to find warehouse quickstart_catalog")

    monkeypatch.setattr(fresh_catalog, "get_catalog", lambda: MissingWarehouseCatalog())

    assert fresh_catalog.list_namespaces() == []
    assert fresh_catalog.list_tables() == []

    status = fresh_catalog.health_check(timeout=1.0)
    assert status["ok"] is True
    assert status["catalog_ready"] is False
    assert "quickstart_catalog" in status["error"]


def test_load_table_returns_none_when_missing(fresh_catalog):
    fresh_catalog.ensure_namespace("aqp")
    assert fresh_catalog.load_table("aqp.never_created") is None


def test_load_table_propagates_real_errors(fresh_catalog, monkeypatch):
    fresh_catalog.ensure_namespace("aqp")

    class _BrokenCatalog:
        def load_table(self, *_args, **_kwargs):
            raise RuntimeError("unexpected catalog backend failure")

    monkeypatch.setattr(fresh_catalog, "get_catalog", lambda: _BrokenCatalog())
    with pytest.raises(RuntimeError, match="unexpected catalog backend failure"):
        fresh_catalog.load_table("aqp.anything")


def test_existing_keys_for_window_uses_predicate_pushdown(fresh_catalog):
    import pandas as pd

    fresh_catalog.ensure_namespace("aqp")
    rows = {
        "vt_symbol": ["AAA", "AAA", "BBB", "CCC"],
        "timestamp": [
            pd.Timestamp("2026-04-01T13:30:00").to_datetime64(),
            pd.Timestamp("2026-04-01T13:31:00").to_datetime64(),
            pd.Timestamp("2026-04-01T13:30:00").to_datetime64(),
            pd.Timestamp("2026-04-02T09:30:00").to_datetime64(),
        ],
        "value": [1.0, 2.0, 3.0, 4.0],
    }
    _seed_table(fresh_catalog, "aqp.intraday_keys", rows)

    keys = fresh_catalog.existing_keys_for_window(
        "aqp.intraday_keys",
        symbols=["AAA", "BBB", "DDD"],
        time_min=pd.Timestamp("2026-04-01T13:00:00"),
        time_max=pd.Timestamp("2026-04-01T23:59:59"),
    )

    symbols_returned = {key[0] for key in keys}
    assert symbols_returned == {"AAA", "BBB"}
    assert len(keys) == 3


def test_existing_keys_for_window_returns_empty_when_table_missing(fresh_catalog):
    keys = fresh_catalog.existing_keys_for_window(
        "aqp.never_loaded",
        symbols=["X"],
        time_min="2026-04-01",
        time_max="2026-04-30",
    )
    assert keys == set()


def test_latest_timestamps_for_symbols_returns_max_per_symbol(fresh_catalog):
    import pandas as pd

    fresh_catalog.ensure_namespace("aqp")
    rows = {
        "vt_symbol": ["AAA", "AAA", "BBB"],
        "timestamp": [
            pd.Timestamp("2026-04-01T13:30:00").to_datetime64(),
            pd.Timestamp("2026-04-01T13:31:00").to_datetime64(),
            pd.Timestamp("2026-04-02T09:30:00").to_datetime64(),
        ],
    }
    _seed_table(fresh_catalog, "aqp.intraday_latest", rows)

    latest = fresh_catalog.latest_timestamps_for_symbols(
        "aqp.intraday_latest",
        symbols=["AAA", "BBB", "ZZZ"],
    )

    assert set(latest.keys()) == {"AAA", "BBB"}
    assert latest["AAA"] == pd.Timestamp("2026-04-01T13:31:00").to_pydatetime()
    assert latest["BBB"] == pd.Timestamp("2026-04-02T09:30:00").to_pydatetime()


def test_latest_timestamps_returns_empty_for_unknown_symbols(fresh_catalog):
    fresh_catalog.ensure_namespace("aqp")
    rows = {
        "vt_symbol": ["AAA"],
        "timestamp": [b"2026-04-01T13:30:00"],
    }
    arrow = pa.table(
        {
            "vt_symbol": pa.array(rows["vt_symbol"], type=pa.string()),
            "timestamp": pa.array(["2026-04-01T13:30:00"], type=pa.string()),
        }
    )
    fresh_catalog.create_or_replace_table("aqp.intraday_latest_empty", arrow.schema)
    fresh_catalog.append_arrow(
        "aqp.intraday_latest_empty",
        arrow,
        create_if_missing=False,
    )

    assert (
        fresh_catalog.latest_timestamps_for_symbols(
            "aqp.intraday_latest_empty",
            symbols=["BBB"],
        )
        == {}
    )


def test_iceberg_diag_returns_status_dict(fresh_catalog):
    from aqp.data import iceberg_diag

    fresh_catalog.ensure_namespace("aqp")
    status = iceberg_diag.collect_status()
    assert status["health"]["ok"] is True
    assert "aqp" in status["namespaces"]
    assert "tables_by_namespace" in status
