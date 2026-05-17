from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pandas as pd


def test_intraday_plan_builds_monthly_components(monkeypatch, tmp_path):
    from aqp.data.sources.alpha_vantage import intraday_plan as mod

    monkeypatch.setattr(mod, "resolve_symbols", lambda *a, **k: ["-P-HIZ.NASDAQ", "AAPL.NASDAQ", "MSFT.NASDAQ"])

    plan = mod.build_intraday_plan(
        symbols="all_active",
        lookback_months=3,
        anchor=date(2026, 4, 27),
        manifest_dir=tmp_path,
    )

    assert len(plan.components) == 9
    assert {component.month for component in plan.components} == {"2026-02", "2026-03", "2026-04"}
    assert {component.interval for component in plan.components} == {"1min"}
    assert plan.manifest_path.endswith(".jsonl")
    assert len(mod.read_components(plan.manifest_path)) == 9
    skipped = [component for component in plan.components if component.ticker == "-P-HIZ"]
    assert len(skipped) == 3
    assert {component.status_reason for component in skipped} == {"unsupported_intraday_ticker"}


def test_intraday_plan_marks_covered_months_skipped(monkeypatch, tmp_path):
    from aqp.data.sources.alpha_vantage import intraday_plan as mod

    monkeypatch.setattr(mod, "resolve_symbols", lambda *a, **k: ["AAPL.NASDAQ"])
    mod.save_delta_state(
        mod.delta_state_path("1min", tmp_path),
        {
            "AAPL.NASDAQ": mod.IntradayDeltaState(
                vt_symbol="AAPL.NASDAQ",
                interval="1min",
                latest_timestamp="2026-03-31T23:59:59",
            )
        },
    )

    plan = mod.build_intraday_plan(
        symbols="all_active",
        lookback_months=3,
        anchor=date(2026, 4, 27),
        manifest_dir=tmp_path,
    )

    statuses = {component.month: component.status for component in plan.components}
    assert statuses["2026-02"] == "skipped"
    assert statuses["2026-03"] == "skipped"
    assert statuses["2026-04"] == "pending"
    reasons = {component.month: component.status_reason for component in plan.components}
    assert reasons["2026-02"] == "covered_by_delta_state"


def test_intraday_loader_filters_existing_timestamp_keys(monkeypatch, tmp_path):
    from aqp.data.sources.alpha_vantage import intraday_backfill as mod
    from aqp.data.sources.alpha_vantage.intraday_plan import (
        IntradayRequestComponent,
        write_components,
    )

    component = IntradayRequestComponent(
        component_id="component-1",
        vt_symbol="AAPL.NASDAQ",
        ticker="AAPL",
        exchange="NASDAQ",
        month="2026-04",
        interval="1min",
        planned_at="2026-04-27T00:00:00+00:00",
    )
    manifest = write_components(tmp_path / "plan.jsonl", [component])
    appended: dict[str, Any] = {}
    registered: dict[str, Any] = {}

    existing_keys_calls: list[dict[str, Any]] = []
    latest_calls: list[dict[str, Any]] = []
    existing_keys = {
        ("AAPL.NASDAQ", pd.Timestamp("2026-04-01T13:30:00")),
    }

    def fake_existing_keys_for_window(identifier, *, symbols, time_min, time_max, **_):
        existing_keys_calls.append(
            {
                "identifier": identifier,
                "symbols": list(symbols),
                "time_min": time_min,
                "time_max": time_max,
            }
        )
        return existing_keys

    def fake_latest_timestamps_for_symbols(identifier, *, symbols, **_):
        latest_calls.append({"identifier": identifier, "symbols": list(symbols)})
        return {"AAPL.NASDAQ": pd.Timestamp("2026-04-01T13:31:00").to_pydatetime()}

    def fake_health_check(*_, **__):
        return {"ok": True, "type": "sql", "uri": "sqlite:///:memory:", "warehouse": ""}

    def fake_append(identifier, table, **kwargs):  # noqa: ARG001
        appended["identifier"] = identifier
        appended["rows"] = table.num_rows
        appended["columns"] = table.column_names

    def fake_register(**kwargs):
        registered.update(kwargs)
        return {"dataset_version_id": "version-1"}

    class _Timeseries:
        def intraday(self, *args, **kwargs):  # noqa: ARG002
            return SimpleNamespace(
                bars=[
                    {
                        "timestamp": "2026-04-01T13:30:00",
                        "open": "1",
                        "high": "2",
                        "low": "1",
                        "close": "2",
                        "volume": "100",
                    },
                    {
                        "timestamp": "2026-04-01T13:31:00",
                        "open": "2",
                        "high": "3",
                        "low": "2",
                        "close": "3",
                        "volume": "200",
                    },
                ]
            )

    class _Client:
        timeseries = _Timeseries()

        def close(self):  # pragma: no cover
            return None

    monkeypatch.setattr(mod.iceberg_catalog, "health_check", fake_health_check)
    monkeypatch.setattr(
        mod.iceberg_catalog,
        "existing_keys_for_window",
        fake_existing_keys_for_window,
    )
    monkeypatch.setattr(
        mod.iceberg_catalog,
        "latest_timestamps_for_symbols",
        fake_latest_timestamps_for_symbols,
    )
    monkeypatch.setattr(mod.iceberg_catalog, "append_arrow", fake_append)
    monkeypatch.setattr(mod, "register_dataset_version", fake_register)
    monkeypatch.setattr(mod, "emit_dataset_properties", lambda **kwargs: True)

    result = mod.IntradayBackfillLoader(client=_Client()).run_manifest(
        manifest,
        batch_size=1,
        cache=False,
    )

    assert result.rows_written == 1
    assert result.duplicate_rows == 1
    assert appended["identifier"] == "aqp_alpha_vantage.time_series_intraday"
    assert appended["rows"] == 1
    assert "request_component_id" in appended["columns"]
    assert registered["iceberg_identifier"] == "aqp_alpha_vantage.time_series_intraday"
    assert registered["load_mode"] == "delta"
    assert existing_keys_calls and existing_keys_calls[0]["symbols"] == ["AAPL.NASDAQ"]
    assert latest_calls and latest_calls[0]["symbols"] == ["AAPL.NASDAQ"]
    updated = mod.read_components(manifest)[0]
    assert updated.status == "completed"
    assert updated.status_reason == "rows_appended"


def test_intraday_loader_aborts_when_iceberg_unhealthy(monkeypatch, tmp_path):
    import pytest

    from aqp.data.sources.alpha_vantage import intraday_backfill as mod
    from aqp.data.sources.alpha_vantage.intraday_plan import (
        IntradayRequestComponent,
        write_components,
    )

    component = IntradayRequestComponent(
        component_id="component-1",
        vt_symbol="AAPL.NASDAQ",
        ticker="AAPL",
        exchange="NASDAQ",
        month="2026-04",
        interval="1min",
        planned_at="2026-04-27T00:00:00+00:00",
    )
    manifest = write_components(tmp_path / "plan.jsonl", [component])

    monkeypatch.setattr(
        mod.iceberg_catalog,
        "health_check",
        lambda **_: {"ok": False, "type": "sql", "uri": "sqlite:///:memory:", "error": "down"},
    )

    class _Client:
        class timeseries:  # pragma: no cover - never invoked
            @staticmethod
            def intraday(*_, **__):
                raise AssertionError("provider must not be called when catalog is unhealthy")

        def close(self):  # pragma: no cover
            return None

    with pytest.raises(RuntimeError, match="Iceberg catalog is not reachable"):
        mod.IntradayBackfillLoader(client=_Client()).run_manifest(
            manifest,
            batch_size=1,
            cache=False,
        )


def test_intraday_loader_skips_provider_payload_rejections(monkeypatch, tmp_path):
    from aqp.data.sources.alpha_vantage import intraday_backfill as mod
    from aqp.data.sources.alpha_vantage._errors import InvalidSymbolError
    from aqp.data.sources.alpha_vantage.intraday_plan import (
        IntradayRequestComponent,
        read_components,
        write_components,
    )

    component = IntradayRequestComponent(
        component_id="component-1",
        vt_symbol="AACOW.NASDAQ",
        ticker="AACOW",
        exchange="NASDAQ",
        month="2026-04",
        interval="1min",
        planned_at="2026-04-27T00:00:00+00:00",
    )
    manifest = write_components(tmp_path / "plan.jsonl", [component])

    monkeypatch.setattr(
        mod.iceberg_catalog,
        "health_check",
        lambda **_: {"ok": True, "type": "sql", "uri": "sqlite:///:memory:", "warehouse": ""},
    )

    class _Client:
        class timeseries:
            @staticmethod
            def intraday(*_, **__):
                raise InvalidSymbolError("Invalid API call")

        def close(self):  # pragma: no cover
            return None

    result = mod.IntradayBackfillLoader(client=_Client()).run_manifest(
        manifest,
        batch_size=1,
        cache=False,
    )

    assert result.components_processed == 1
    assert result.rows_written == 0
    assert result.results[0].status == "skipped"
    updated = read_components(manifest)[0]
    assert updated.status == "skipped"
    assert updated.status_reason == "provider_rejected_component"


def test_intraday_plan_summary_omits_component_payload(monkeypatch, tmp_path):
    from aqp.data.sources.alpha_vantage import intraday_plan as mod
    from aqp.tasks.ingestion_tasks import _intraday_plan_summary

    monkeypatch.setattr(mod, "resolve_symbols", lambda *a, **k: ["AAPL.NASDAQ"])
    plan = mod.build_intraday_plan(
        symbols="all_active",
        lookback_months=2,
        anchor=date(2026, 4, 27),
        manifest_dir=tmp_path,
    )

    summary = _intraday_plan_summary(plan)

    assert summary["component_count"] == 2
    assert summary["symbol_count"] == 1
    assert summary["months"] == ["2026-03", "2026-04"]
    assert "components" not in summary


def test_datahub_emit_disabled_without_url(monkeypatch):
    from aqp.config import settings
    from aqp.data.sources.alpha_vantage.datahub import emit_dataset_properties

    monkeypatch.setattr(settings, "datahub_gms_url", "", raising=False)

    assert emit_dataset_properties(platform="iceberg", name="x.y", description="test") is False


def test_intraday_run_guard_blocks_restart_storm(monkeypatch, tmp_path):
    from aqp.config import settings
    from aqp.data.sources.alpha_vantage.intraday_backfill import record_run_start_or_raise

    monkeypatch.setattr(settings, "alpha_vantage_intraday_run_guard_max_starts", 2, raising=False)
    monkeypatch.setattr(settings, "alpha_vantage_intraday_run_guard_window_seconds", 3600, raising=False)
    manifest = tmp_path / "plan.jsonl"

    record_run_start_or_raise(manifest)
    record_run_start_or_raise(manifest)

    try:
        record_run_start_or_raise(manifest)
    except RuntimeError as exc:
        assert "run guard tripped" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected run guard to reject third start")
