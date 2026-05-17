"""Tests for medallion validation + time-travel signature in iceberg_catalog."""
from __future__ import annotations

import inspect

import pytest

from aqp.data.catalog.active_metadata import (
    LAYER_PREFIXES,
    validate_layer_for_namespace,
)


def test_layer_prefixes_match_doc() -> None:
    assert LAYER_PREFIXES == {
        "bronze": "aqp_bronze_",
        "silver": "aqp_silver_",
        "gold": "aqp_gold_",
    }


def test_validate_layer_for_namespace_each_layer() -> None:
    validate_layer_for_namespace("bronze", "aqp_bronze_alpha_vantage.daily_bars")
    validate_layer_for_namespace("silver", "aqp_silver_alpha_vantage.daily_bars")
    validate_layer_for_namespace("gold", "aqp_gold_equity.feature_set")


def test_validate_layer_for_namespace_rejects_legacy_when_layer_set() -> None:
    with pytest.raises(ValueError):
        validate_layer_for_namespace("silver", "aqp_alpha_vantage.daily_bars")


def test_append_arrow_has_medallion_kwargs() -> None:
    """Signature smoke test — guarantees backwards-compat kwargs exist.

    We don't actually call ``append_arrow`` here because pyiceberg may
    not be importable in the hermetic test environment; introspecting
    the signature is enough to guard against accidental param removal.
    """
    from aqp.data.iceberg_catalog import append_arrow

    sig = inspect.signature(append_arrow)
    expected_params = {
        "medallion_layer",
        "business_metadata",
        "data_contract",
        "actor",
        "run_id",
        "manifest_id",
        "service_name",
        "register_metadata",
    }
    assert expected_params.issubset(set(sig.parameters))


def test_read_arrow_at_signature() -> None:
    from aqp.data.iceberg_catalog import read_arrow_at

    sig = inspect.signature(read_arrow_at)
    expected_params = {"identifier", "snapshot_id", "as_of", "columns", "limit", "row_filter"}
    assert expected_params.issubset(set(sig.parameters))
