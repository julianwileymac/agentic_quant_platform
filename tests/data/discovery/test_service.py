"""Pure-Python tests for ``DiscoveryService`` lifecycle classification.

These tests don't touch Postgres or Iceberg — they exercise the
in-memory transformation logic on synthetic rows. Integration tests
that hit a real DB live under :file:`tests/api/`.
"""
from __future__ import annotations

from types import SimpleNamespace

from aqp.data.discovery.service import DiscoveryService


def _row(**kwargs):
    defaults = {
        "id": "row-1",
        "name": "demo",
        "provider": "self_service",
        "domain": "user.dataset",
        "iceberg_identifier": None,
        "load_mode": "discovered",
        "source_uri": None,
        "description": None,
        "tags": [],
        "medallion_layer": None,
        "business_metadata": {},
        "data_contract_json": {},
        "dataset_kind": None,
        "is_ingested": None,
        "spec_hash": None,
        "external_spec_json": None,
        "updated_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_ingested_row_classifies_as_ingested() -> None:
    svc = DiscoveryService()
    entry = svc._row_to_entry(  # noqa: SLF001 — direct test of helper
        _row(
            id="r-ingested",
            iceberg_identifier="aqp_silver_demo.bars",
            is_ingested=True,
            dataset_kind="iceberg",
        )
    )
    assert entry.lifecycle_state == "ingested"
    assert entry.dataset_kind == "iceberg"
    assert entry.is_ingested is True
    assert entry.namespace == "aqp_silver_demo"
    assert entry.medallion_layer is None or entry.medallion_layer == "silver"


def test_external_row_classifies_as_external_only() -> None:
    svc = DiscoveryService()
    entry = svc._row_to_entry(  # noqa: SLF001
        _row(
            id="r-external",
            external_spec_json={
                "intent_kind": "external",
                "source_uri": "https://api.example.com/v1",
                "docs_url": "https://example.com/docs",
            },
            is_ingested=False,
            dataset_kind="external",
        )
    )
    assert entry.lifecycle_state == "external_only"
    assert entry.is_ingested is False
    assert entry.docs_url == "https://example.com/docs"


def test_pending_row_without_external_spec_or_iceberg_id() -> None:
    svc = DiscoveryService()
    entry = svc._row_to_entry(_row(id="r-pending"))  # noqa: SLF001
    assert entry.lifecycle_state == "pending"
    assert entry.is_ingested is False


def test_layer_for_namespace() -> None:
    from aqp.data.discovery.service import _layer_for_namespace

    assert _layer_for_namespace("aqp_bronze_demo") == "bronze"
    assert _layer_for_namespace("aqp_silver_demo") == "silver"
    assert _layer_for_namespace("aqp_gold_demo") == "gold"
    assert _layer_for_namespace("aqp_demo") is None
    assert _layer_for_namespace(None) is None


def test_dedupe_key_lowercases() -> None:
    from aqp.data.discovery.service import _dedupe_key
    from aqp.data.discovery.types import DiscoveryEntry

    a = DiscoveryEntry(
        id="a",
        name="MyDataset",
        provider="Vendor",
        lifecycle_state="pending",
    )
    b = DiscoveryEntry(
        id="b",
        name="mydataset",
        provider="vendor",
        lifecycle_state="ingested",
    )
    assert _dedupe_key(a) == _dedupe_key(b)
