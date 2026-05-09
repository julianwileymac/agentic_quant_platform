from __future__ import annotations

import pytest
from fastapi import HTTPException

from aqp.api.routes import metadata_catalog


def test_patch_metadata_dataset_forwards_updates(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeService:
        def patch_dataset(self, dataset_id: str, **values):  # type: ignore[no-untyped-def]
            captured["dataset_id"] = dataset_id
            captured["values"] = values
            return {
                "id": dataset_id,
                "name": "bars.default",
                "provider": "yfinance",
                "domain": "market.bars",
                "tags": values.get("tags", []),
                "description": values.get("description"),
                "load_mode": values.get("load_mode", "managed"),
            }

    monkeypatch.setattr(metadata_catalog, "_service", FakeService())

    payload = metadata_catalog.MetadataDatasetPatchRequest(
        description="Updated description",
        tags=["equity", "daily"],
        load_mode="managed",
    )
    result = metadata_catalog.patch_metadata_dataset("dataset-123", payload)

    assert captured["dataset_id"] == "dataset-123"
    assert captured["values"] == {
        "description": "Updated description",
        "tags": ["equity", "daily"],
        "load_mode": "managed",
    }
    assert result["id"] == "dataset-123"
    assert result["description"] == "Updated description"


def test_patch_metadata_dataset_requires_fields() -> None:
    with pytest.raises(HTTPException) as exc:
        metadata_catalog.patch_metadata_dataset(
            "dataset-123",
            metadata_catalog.MetadataDatasetPatchRequest(),
        )
    assert exc.value.status_code == 400


def test_patch_metadata_dataset_404_when_missing(monkeypatch) -> None:
    class FakeService:
        def patch_dataset(self, dataset_id: str, **values):  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr(metadata_catalog, "_service", FakeService())

    with pytest.raises(HTTPException) as exc:
        metadata_catalog.patch_metadata_dataset(
            "missing-id",
            metadata_catalog.MetadataDatasetPatchRequest(description="x"),
        )
    assert exc.value.status_code == 404


def test_patch_metadata_dataset_translates_validation_errors(monkeypatch) -> None:
    class FakeService:
        def patch_dataset(self, dataset_id: str, **values):  # type: ignore[no-untyped-def]
            raise ValueError("unsupported load_mode")

    monkeypatch.setattr(metadata_catalog, "_service", FakeService())

    with pytest.raises(HTTPException) as exc:
        metadata_catalog.patch_metadata_dataset(
            "dataset-123",
            metadata_catalog.MetadataDatasetPatchRequest(load_mode="bad-mode"),
        )
    assert exc.value.status_code == 400
