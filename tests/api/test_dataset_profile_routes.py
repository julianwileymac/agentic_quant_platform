from __future__ import annotations

import pyarrow as pa


def test_profile_table_suggests_identifier_columns(monkeypatch):
    from aqp.api.routes import datasets

    table = pa.Table.from_pylist(
        [
            {"vt_symbol": "AAPL.NASDAQ", "close": 100.0},
            {"vt_symbol": "MSFT.NASDAQ", "close": 200.0},
        ]
    )

    monkeypatch.setattr(datasets.iceberg_catalog, "get_catalog", lambda: object())
    monkeypatch.setattr(datasets.iceberg_catalog, "read_arrow", lambda identifier, limit=None: table)  # noqa: ARG005
    monkeypatch.setattr(datasets, "_matched_identifier_count", lambda scheme, values: 1)  # noqa: ARG005

    payload = datasets.profile_table("aqp", "bars")

    assert payload.iceberg_identifier == "aqp.bars"
    assert payload.identifier_suggestions
    assert payload.identifier_suggestions[0].scheme == "vt_symbol"
