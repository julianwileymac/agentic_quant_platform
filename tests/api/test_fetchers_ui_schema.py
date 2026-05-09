"""Fetcher UI schema tests."""
from __future__ import annotations

from aqp.api.routes import fetchers
from aqp.data.engine.manifest import FetchSliceSpec


def test_fetch_slice_spec_drops_empty_values():
    spec = FetchSliceSpec(symbols=["SPY"], interval="1d", limit=10)

    assert spec.to_source_kwargs() == {
        "symbols": ["SPY"],
        "symbol_mode": "explicit",
        "interval": "1d",
        "limit": 10,
        "offset": 0,
    }


def test_fetcher_ui_schema_includes_common_slice_fields(monkeypatch):
    monkeypatch.setattr(
        fetchers,
        "get_node_schema",
        lambda node_name: {
            "name": node_name,
            "class_name": "DummySource",
            "module": "tests",
            "doc": "",
            "fields": [
                {
                    "name": "api_key",
                    "annotation": "str",
                    "required": False,
                    "default": None,
                }
            ],
        },
    )

    schema = fetchers.get_node_ui_schema("source.dummy")
    field_names = {field["name"] for field in schema["fields"]}

    assert {"symbols", "date_range", "interval", "limit", "offset"} <= field_names
    assert "kwargs.api_key" in field_names
    assert "properties" in schema["slice_model"]
