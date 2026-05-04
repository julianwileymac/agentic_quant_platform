"""Unit tests for ``aqp.visualization.superset_sync``.

The full ``sync_superset_assets`` flow is exercised against a fake
``SupersetClient`` so we can assert the upsert ordering (database →
datasets → charts → dashboards) without spinning up Superset.
"""
from __future__ import annotations

from typing import Any


class _FakeSupersetClient:
    """Minimal stand-in for :class:`aqp.services.superset_client.SupersetClient`.

    Records every call against an in-memory store and returns the same
    deterministic ids the upsert helpers expect (``{"id": N}``).
    """

    def __init__(self) -> None:
        self.databases: list[dict[str, Any]] = []
        self.datasets: list[dict[str, Any]] = []
        self.charts: list[dict[str, Any]] = []
        self.dashboards: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_id = 100

    # context manager hooks (unused — the test owns the lifetime)
    def __enter__(self) -> "_FakeSupersetClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def close(self) -> None:
        return None

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    # database
    def list_databases(self) -> list[dict[str, Any]]:
        return list(self.databases)

    def create_database(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_database", payload))
        row = {"id": self._id(), **payload}
        self.databases.append(row)
        return {"id": row["id"], "result": row}

    def update_database(self, database_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_database", {"id": database_id, **payload}))
        return {"id": database_id, "result": payload}

    # dataset
    def list_datasets(self) -> list[dict[str, Any]]:
        return list(self.datasets)

    def create_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_dataset", payload))
        row = {"id": self._id(), **payload}
        self.datasets.append(row)
        return {"id": row["id"], "result": row}

    def update_dataset(self, dataset_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_dataset", {"id": dataset_id, **payload}))
        return {"id": dataset_id, "result": payload}

    # chart
    def list_charts(self) -> list[dict[str, Any]]:
        return list(self.charts)

    def create_chart(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_chart", payload))
        row = {"id": self._id(), **payload}
        self.charts.append(row)
        return {"id": row["id"], "result": row}

    def update_chart(self, chart_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_chart", {"id": chart_id, **payload}))
        return {"id": chart_id, "result": payload}

    # dashboard
    def list_dashboards(self) -> list[dict[str, Any]]:
        return list(self.dashboards)

    def create_dashboard(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_dashboard", payload))
        row = {"id": self._id(), **payload}
        self.dashboards.append(row)
        return {"id": row["id"], "result": row}

    def update_dashboard(self, dashboard_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("update_dashboard", {"id": dashboard_id, **payload}))
        return {"id": dashboard_id, "result": payload}


def test_sync_creates_database_then_datasets_then_charts(monkeypatch) -> None:
    from aqp.visualization import superset_sync
    from aqp.visualization.superset_sync import sync_superset_assets

    monkeypatch.setattr(
        superset_sync,
        "build_current_asset_plan",
        lambda: superset_sync.build_asset_plan(
            available_identifiers=["aqp_equity.sp500_daily", "aqp_macro.fred_basket"]
        ),
    )

    fake = _FakeSupersetClient()
    result = sync_superset_assets(client=fake)

    methods = [name for name, _ in fake.calls]
    # Database first, then every dataset, then every chart, then dashboard.
    assert methods[0] == "create_database"
    assert methods.count("create_dataset") == 2
    assert "create_chart" in methods
    assert "create_dashboard" in methods

    # Result wires the right identifiers back to ids.
    assert set(result["dataset_ids"]) == {"aqp_equity.sp500_daily", "aqp_macro.fred_basket"}
    assert result["chart_ids"]
    assert result["dashboard_ids"]


def test_sync_updates_existing_database_in_place(monkeypatch) -> None:
    from aqp.visualization import superset_sync
    from aqp.visualization.superset_sync import sync_superset_assets

    monkeypatch.setattr(
        superset_sync,
        "build_current_asset_plan",
        lambda: superset_sync.build_asset_plan(available_identifiers=["aqp_equity.sp500_daily"]),
    )

    fake = _FakeSupersetClient()
    fake.databases.append({"id": 7, "database_name": "AQP Trino Iceberg"})

    result = sync_superset_assets(client=fake)

    # Database was updated rather than created.
    assert ("update_database", {"id": 7, "database_name": "AQP Trino Iceberg"}) in [
        (name, {k: payload[k] for k in ["id", "database_name"]})
        for name, payload in fake.calls
        if name == "update_database"
    ]
    assert result["database_id"] == 7
