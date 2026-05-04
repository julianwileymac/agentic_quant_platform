from __future__ import annotations

import pyarrow as pa
import pytest


def _stub_iceberg(monkeypatch, table: pa.Table) -> None:
    """Wire a deterministic Iceberg backend onto the renderer."""

    from aqp.visualization import bokeh_renderer

    monkeypatch.setattr(
        bokeh_renderer.iceberg_catalog,
        "read_arrow",
        lambda identifier, limit=None: table,  # noqa: ARG005
    )
    monkeypatch.setattr(
        bokeh_renderer.iceberg_catalog,
        "load_table",
        lambda identifier: None,  # noqa: ARG005
    )


def test_bokeh_renderer_returns_json_item(monkeypatch, tmp_path) -> None:
    pytest.importorskip("bokeh")
    from aqp.config import settings
    from aqp.visualization import bokeh_renderer
    from aqp.visualization.bokeh_renderer import BokehChartSpec

    table = pa.Table.from_pylist(
        [
            {"timestamp": "2024-01-01", "vt_symbol": "AAPL.NASDAQ", "close": 100.0},
            {"timestamp": "2024-01-02", "vt_symbol": "AAPL.NASDAQ", "close": 101.0},
        ]
    )
    monkeypatch.setattr(settings, "visualization_cache_dir", tmp_path)
    # File-only cache so the test never reaches a real Redis instance.
    monkeypatch.setattr(settings, "visualization_cache_backend", "file")
    _stub_iceberg(monkeypatch, table)

    item = bokeh_renderer.render_bokeh_item(
        BokehChartSpec(
            dataset_identifier="aqp_equity.sp500_daily",
            target_id="plot",
            x="timestamp",
            y="close",
        )
    )

    assert item["target_id"] == "plot"
    assert item["root_id"]
    assert item["doc"]
    assert item["version"]
    assert item["cache_key"]


def test_bokeh_renderer_serves_second_call_from_cache(monkeypatch, tmp_path) -> None:
    pytest.importorskip("bokeh")
    from aqp.config import settings
    from aqp.visualization import bokeh_renderer
    from aqp.visualization.bokeh_renderer import BokehChartSpec

    table = pa.Table.from_pylist(
        [
            {"timestamp": "2024-01-01", "vt_symbol": "AAPL.NASDAQ", "close": 100.0},
            {"timestamp": "2024-01-02", "vt_symbol": "AAPL.NASDAQ", "close": 101.0},
        ]
    )
    monkeypatch.setattr(settings, "visualization_cache_dir", tmp_path)
    monkeypatch.setattr(settings, "visualization_cache_backend", "file")

    call_count = {"n": 0}

    def counting_read_arrow(identifier, limit=None):  # noqa: ARG001
        call_count["n"] += 1
        return table

    monkeypatch.setattr(bokeh_renderer.iceberg_catalog, "read_arrow", counting_read_arrow)
    monkeypatch.setattr(bokeh_renderer.iceberg_catalog, "load_table", lambda identifier: None)  # noqa: ARG005

    spec = BokehChartSpec(
        dataset_identifier="aqp_equity.sp500_daily",
        target_id="plot",
        x="timestamp",
        y="close",
    )
    first = bokeh_renderer.render_bokeh_item(spec)
    second = bokeh_renderer.render_bokeh_item(spec)

    # Same cache key both times AND the source scan ran exactly once.
    assert first["cache_key"] == second["cache_key"]
    assert call_count["n"] == 1


def test_clear_cache_removes_file_entries(monkeypatch, tmp_path) -> None:
    pytest.importorskip("bokeh")
    from aqp.config import settings
    from aqp.visualization import bokeh_renderer
    from aqp.visualization.bokeh_renderer import BokehChartSpec, clear_cache

    monkeypatch.setattr(settings, "visualization_cache_dir", tmp_path)
    monkeypatch.setattr(settings, "visualization_cache_backend", "file")
    table = pa.Table.from_pylist(
        [{"timestamp": "2024-01-01", "vt_symbol": "AAPL.NASDAQ", "close": 100.0}]
    )
    _stub_iceberg(monkeypatch, table)

    bokeh_renderer.render_bokeh_item(
        BokehChartSpec(
            dataset_identifier="aqp_equity.sp500_daily",
            target_id="plot",
            x="timestamp",
            y="close",
        )
    )
    assert any(tmp_path.glob("*.json"))
    summary = clear_cache()
    assert summary["file"] >= 1
    assert not list(tmp_path.glob("*.json"))


def test_redis_cache_is_consulted_when_enabled(monkeypatch, tmp_path) -> None:
    pytest.importorskip("bokeh")
    from aqp.config import settings
    from aqp.visualization import bokeh_renderer
    from aqp.visualization.bokeh_renderer import BokehChartSpec

    monkeypatch.setattr(settings, "visualization_cache_dir", tmp_path)
    monkeypatch.setattr(settings, "visualization_cache_backend", "both")

    table = pa.Table.from_pylist(
        [{"timestamp": "2024-01-01", "vt_symbol": "AAPL.NASDAQ", "close": 100.0}]
    )
    _stub_iceberg(monkeypatch, table)

    store: dict[str, str] = {}

    class FakeRedis:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def get(self, key: str) -> str | None:
            self.calls.append(("get", key))
            return store.get(key)

        def setex(self, key: str, ttl: int, value: str) -> None:  # noqa: ARG002
            self.calls.append(("setex", key))
            store[key] = value

        def set(self, key: str, value: str) -> None:
            self.calls.append(("set", key))
            store[key] = value

        def scan_iter(self, match: str):  # noqa: ANN001, D401
            for key in list(store):
                if key.startswith(match.rstrip("*")):
                    yield key

        def delete(self, key: str) -> None:
            store.pop(key, None)

        def ttl(self, key: str) -> int:  # noqa: ARG002
            return 600

    fake = FakeRedis()
    monkeypatch.setattr(bokeh_renderer, "_redis_client", lambda: fake)

    spec = BokehChartSpec(
        dataset_identifier="aqp_equity.sp500_daily",
        target_id="plot",
        x="timestamp",
        y="close",
    )
    bokeh_renderer.render_bokeh_item(spec)
    bokeh_renderer.render_bokeh_item(spec)

    methods = [c[0] for c in fake.calls]
    # First call: GET → miss, SETEX (write). Second call: GET → hit (no rewrite).
    assert methods.count("get") == 2
    assert methods.count("setex") == 1
