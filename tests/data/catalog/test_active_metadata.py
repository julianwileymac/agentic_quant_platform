"""Active metadata + medallion validation tests."""
from __future__ import annotations

import pytest

from aqp.data.catalog import (
    BusinessMetadata,
    DataContract,
    namespace_for_layer,
    register_dataset,
    validate_layer_for_namespace,
)
from aqp.data.catalog.active_metadata import validate_contract_against_schema


def test_namespace_for_layer_builds_canonical_prefix() -> None:
    assert namespace_for_layer("bronze", "alpha_vantage") == "aqp_bronze_alpha_vantage"
    assert namespace_for_layer("silver", "Alpha_Vantage") == "aqp_silver_alpha_vantage"
    assert namespace_for_layer("gold", "_yfinance_") == "aqp_gold_yfinance"


def test_namespace_for_layer_rejects_unknown_layer() -> None:
    with pytest.raises(ValueError):
        namespace_for_layer("platinum", "alpha_vantage")  # type: ignore[arg-type]


def test_namespace_for_layer_rejects_empty_suffix() -> None:
    with pytest.raises(ValueError):
        namespace_for_layer("bronze", "")


def test_validate_layer_for_namespace_accepts_matching_prefix() -> None:
    validate_layer_for_namespace("bronze", "aqp_bronze_alpha_vantage.daily_bars")
    validate_layer_for_namespace("silver", "aqp_silver_macro.fred_observations")
    validate_layer_for_namespace("gold", "aqp_gold_equity.daily_features")


def test_validate_layer_for_namespace_rejects_mismatched_prefix() -> None:
    with pytest.raises(ValueError):
        validate_layer_for_namespace("silver", "aqp_bronze_alpha_vantage.daily_bars")


def test_validate_layer_for_namespace_accepts_none_layer() -> None:
    validate_layer_for_namespace(None, "aqp_legacy_table")


def test_validate_contract_with_required_columns() -> None:
    pa = pytest.importorskip("pyarrow")
    schema = pa.schema(
        [
            pa.field("vt_symbol", pa.string()),
            pa.field("close", pa.float64()),
            pa.field("volume", pa.int64()),
        ]
    )
    contract = DataContract(
        columns=[
            {"name": "vt_symbol", "type": "string", "required": True},
            {"name": "close", "type": "float", "required": True},
            {"name": "missing_col", "type": "int", "required": True},
        ]
    )
    violations = validate_contract_against_schema(contract, schema)
    assert any("missing_col" in v for v in violations)
    assert not any("vt_symbol" in v for v in violations)


def test_validate_contract_detects_type_family_mismatch() -> None:
    pa = pytest.importorskip("pyarrow")
    schema = pa.schema([pa.field("close", pa.string())])
    contract = DataContract(
        columns=[{"name": "close", "type": "float", "required": True}]
    )
    violations = validate_contract_against_schema(contract, schema)
    assert any("close" in v and "float" in v for v in violations)


def test_register_dataset_upserts_catalog_row(in_memory_db) -> None:
    from sqlalchemy import select

    from aqp.persistence.models import DatasetCatalog

    pa = pytest.importorskip("pyarrow")
    schema = pa.schema(
        [
            pa.field("vt_symbol", pa.string()),
            pa.field("close", pa.float64()),
        ]
    )
    bm = BusinessMetadata(
        data_owner="data-team",
        semantic_definition="Daily close prices.",
        reliability_score=0.9,
        sla_class="tier-2-eod",
        domain="market.bars",
    )
    contract = DataContract(
        columns=[
            {"name": "vt_symbol", "type": "string", "required": True},
            {"name": "close", "type": "float", "required": True},
        ]
    )
    result = register_dataset(
        "aqp_silver_alpha_vantage.daily_bars",
        medallion_layer="silver",
        business_metadata=bm,
        data_contract=contract,
        arrow_schema=schema,
        provider="alpha_vantage",
    )
    assert result.created is True
    assert result.medallion_layer == "silver"
    assert result.contract_violations == []

    Session = in_memory_db
    with Session() as session:
        row = (
            session.execute(
                select(DatasetCatalog).where(
                    DatasetCatalog.iceberg_identifier
                    == "aqp_silver_alpha_vantage.daily_bars"
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        assert row.medallion_layer == "silver"
        assert row.business_metadata["data_owner"] == "data-team"
        assert row.business_metadata["reliability_score"] == 0.9


def test_register_dataset_rejects_layer_mismatch() -> None:
    bm = BusinessMetadata(data_owner="t", semantic_definition="d")
    with pytest.raises(ValueError):
        register_dataset(
            "aqp_bronze_alpha_vantage.daily_bars",
            medallion_layer="silver",
            business_metadata=bm,
        )


def test_register_dataset_is_idempotent(in_memory_db) -> None:
    bm = BusinessMetadata(data_owner="t", semantic_definition="d")
    first = register_dataset(
        "aqp_silver_alpha_vantage.daily_bars",
        medallion_layer="silver",
        business_metadata=bm,
        provider="alpha_vantage",
    )
    second = register_dataset(
        "aqp_silver_alpha_vantage.daily_bars",
        medallion_layer="silver",
        business_metadata=bm,
        provider="alpha_vantage",
    )
    assert first.catalog_id == second.catalog_id
    assert first.created is True
    assert second.created is False


def test_dataset_decorator_attaches_spec() -> None:
    from aqp.data.catalog import dataset

    @dataset(
        layer="silver",
        owner="data-team",
        semantic_definition="Test dataset.",
        reliability=0.5,
    )
    class _MySink:
        pass

    spec = getattr(_MySink, "__aqp_dataset__", None)
    assert spec is not None
    assert spec["layer"] == "silver"
    assert spec["business_metadata"].data_owner == "data-team"
