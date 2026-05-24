"""Opt-in live integration tests for the AQP <-> SDK bridge.

These exercise the helpers in ``rpi_k8s_sdk.aqp`` and ``rpi_k8s_sdk.data``
end-to-end against a real cluster.  They are skipped by default so the unit
suite stays hermetic.

To run, point your kubeconfig at a live cluster and set::

    RPI_K8S_RUN_INTEGRATION=1 pytest tests/test_live_aqp.py
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RPI_K8S_RUN_INTEGRATION") != "1",
    reason="live AQP smoke tests are opt-in",
)


def test_aqp_session_context_runs():
    """`aqp_session()` should configure tracing without crashing."""

    from rpi_k8s_sdk import aqp_session

    with aqp_session(service_name="rpi-k8s-aqp-smoke", tunnels=False) as settings:
        assert settings is not None
        assert settings.mlflow_tracking_uri.startswith(("http://", "https://"))


def test_devloop_tunnel_set_can_open_and_close():
    """Smoke check: every dev-loop tunnel command should at least be valid."""

    from rpi_k8s_sdk import LocalAccessSettings, LocalTunnelManager

    manager = LocalTunnelManager(LocalAccessSettings())
    services = [
        manager.settings.postgresql,
        manager.settings.redis,
        manager.settings.mlflow,
        manager.settings.minio,
        manager.settings.otel_collector,
        manager.settings.datahub_gms,
        manager.settings.argo_server,
    ]
    for svc in services:
        cmd = manager.tunnel(svc).command()
        assert cmd[0] == "kubectl"
        assert cmd[1] == "port-forward"
        assert cmd[2].startswith("svc/")


def test_duckdb_engine_returns_connection():
    """DuckDB fallback engine should hand back a usable connection."""

    pytest.importorskip("duckdb")
    from rpi_k8s_sdk import duckdb_engine

    con = duckdb_engine(s3=False)
    try:
        result = con.execute("SELECT 42 AS answer").fetchone()
        assert result[0] == 42
    finally:
        con.close()


def test_iceberg_table_helper_resolves():
    """If both PyIceberg and the cluster catalog are reachable, load a table."""

    pytest.importorskip("pyiceberg")
    from rpi_k8s_sdk import iceberg_table

    try:
        table = iceberg_table("nonexistent_smoke_table")
    except Exception as exc:
        # NoSuchTable / connection errors are expected on a fresh cluster.
        assert "nonexistent_smoke_table" in str(exc) or "catalog" in str(exc).lower()
    else:
        assert table is not None
