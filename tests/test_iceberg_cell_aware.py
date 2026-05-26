"""Phase 6 §9.3 — cell-aware Iceberg catalog properties.

When a request is bound to a deployment cell via the Phase 3 §6.3
``aqp.tenancy.runtime_context``, the per-cell ``data_plane.iceberg_*``
endpoints supersede the cluster-wide ``settings.iceberg_*`` seeds. The
helpers in this test exercise the resolution path without booting a
real PyIceberg client.
"""
from __future__ import annotations

import pytest

from aqp.data import iceberg_catalog
from aqp.tenancy.runtime_context import (
    reset_runtime_context,
    set_runtime_context,
)


class _FakeCtx:
    """Minimal runtime-context stand-in carrying just ``cell_id``."""

    def __init__(self, cell_id: str | None) -> None:
        self.cell_id = cell_id


@pytest.fixture(autouse=True)
def _evict_catalog_cache():
    """Phase 6 §9.3 — guarantee a clean cell-keyed cache per test."""
    iceberg_catalog.reset_catalog_cache()
    yield
    iceberg_catalog.reset_catalog_cache()


def test_cell_data_plane_returns_none_without_context() -> None:
    """CLI / bootstrap path: no request context, no cell data plane."""
    assert iceberg_catalog._cell_data_plane() is None
    assert iceberg_catalog._active_cell_id() is None


def test_cell_data_plane_returns_none_when_cell_id_unset() -> None:
    """A context with ``cell_id=None`` (legacy un-celled call) keeps falling back."""
    token = set_runtime_context(_FakeCtx(cell_id=None))
    try:
        assert iceberg_catalog._cell_data_plane() is None
        assert iceberg_catalog._active_cell_id() is None
    finally:
        reset_runtime_context(token)


def test_cell_data_plane_returns_none_for_legacy_local_cell() -> None:
    """The ``cell-shared-std-local`` seed has an empty data plane: fall back."""
    token = set_runtime_context(_FakeCtx(cell_id="cell-shared-std-local"))
    try:
        # All data_plane fields default to "" for the local cell, which
        # means ``_cell_data_plane`` returns None (legacy shared path).
        assert iceberg_catalog._cell_data_plane() is None
        assert iceberg_catalog._active_cell_id() == "cell-shared-std-local"
    finally:
        reset_runtime_context(token)


def test_cell_data_plane_resolves_for_us_east_1a_shared_std() -> None:
    """The provisioning ``cell-shared-std-us-east-1a`` has a populated data plane."""
    token = set_runtime_context(_FakeCtx(cell_id="cell-shared-std-us-east-1a"))
    try:
        dp = iceberg_catalog._cell_data_plane()
        assert dp is not None, "Phase 6 data plane should resolve for us-east-1a"
        assert dp.iceberg_rest_uri.endswith(":8181")
        assert dp.iceberg_warehouse_uri.startswith("s3://aqp-cell-shared-std-us-east-1a-warehouse")
        assert dp.minio_endpoint.endswith(":9000")
        assert iceberg_catalog._active_cell_id() == "cell-shared-std-us-east-1a"
    finally:
        reset_runtime_context(token)


def test_build_properties_uses_cell_iceberg_rest_uri() -> None:
    """``_build_properties`` MUST override ``settings.iceberg_rest_uri``."""
    token = set_runtime_context(_FakeCtx(cell_id="cell-shared-std-us-east-1a"))
    try:
        props = iceberg_catalog._build_properties()
    finally:
        reset_runtime_context(token)

    assert props.get("type") == "rest"
    # The cell URI wins over settings.iceberg_rest_uri.
    assert props.get("uri", "").endswith(":8181")
    assert "cell-shared-std-us-east-1a" in props.get("uri", "")
    # Warehouse points at the per-cell MinIO bucket.
    assert props.get("warehouse", "").startswith("s3://aqp-cell-shared-std-us-east-1a-warehouse")
    # S3 endpoint points at the per-cell MinIO Service.
    assert "cell-shared-std-us-east-1a" in props.get("s3.endpoint", "")


def test_build_properties_falls_back_to_settings_without_cell() -> None:
    """Without a cell binding, ``_build_properties`` MUST use settings."""
    # Ensure no context is bound.
    props = iceberg_catalog._build_properties()
    assert props.get("type") in {"rest", "sql"}
    # The settings.iceberg_rest_uri value (or sql fallback) wins.
    uri = props.get("uri", "")
    assert "cell-shared-std-us-east-1a" not in uri
    assert "cell-shared-prem-us-east-1a" not in uri
    assert "cell-silo-reg-acme" not in uri


def test_silo_reg_cell_uses_dedicated_endpoints() -> None:
    """``cell-silo-reg-acme`` MUST have its own per-cell endpoints (FINRA posture)."""
    token = set_runtime_context(_FakeCtx(cell_id="cell-silo-reg-acme"))
    try:
        dp = iceberg_catalog._cell_data_plane()
    finally:
        reset_runtime_context(token)
    assert dp is not None
    assert "cell-silo-reg-acme" in dp.iceberg_rest_uri
    assert "cell-silo-reg-acme" in dp.iceberg_warehouse_uri
    assert "cell-silo-reg-acme" in dp.minio_endpoint
    # Phase 6 §9.7 — silo-reg cells MUST set vault_transit_key.
    assert dp.vault_transit_key == "aqp-cell-silo-reg-acme"


def test_unknown_cell_id_falls_back_to_settings() -> None:
    """An unknown cell id MUST fall back to ``settings.*`` (no error)."""
    token = set_runtime_context(_FakeCtx(cell_id="cell-does-not-exist"))
    try:
        dp = iceberg_catalog._cell_data_plane()
    finally:
        reset_runtime_context(token)
    assert dp is None
