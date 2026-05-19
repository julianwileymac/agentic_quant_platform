"""ConnectivityConfig — env precedence + service resolution."""
from __future__ import annotations

import pytest

from aqp_platform_core.connectivity import (
    ConnectivityConfig,
    reset_connectivity_config,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    reset_connectivity_config()


def test_defaults_resolve_to_compose_dns() -> None:
    cfg = ConnectivityConfig()

    core = cfg.route_for("core")
    assert core.base_url == "http://aqp-core:8000"
    assert core.source == "default"

    cp = cfg.route_for("control_plane")
    assert cp.base_url == "http://aqp-cp:9000"
    assert cp.source == "default"


def test_env_override_marks_source_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_CORE_API_URL", "http://aqp-core.default.svc.cluster.local")
    reset_connectivity_config()
    cfg = ConnectivityConfig()

    core = cfg.route_for("core")
    assert core.base_url == "http://aqp-core.default.svc.cluster.local"
    assert core.source == "env"


def test_ingress_base_url_wins_over_per_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AQP_INGRESS_BASE_URL", "https://api.aqp.enterprise.com")
    monkeypatch.setenv("AQP_CORE_API_URL", "http://ignored")
    reset_connectivity_config()
    cfg = ConnectivityConfig()

    core = cfg.route_for("core")
    assert core.base_url == "https://api.aqp.enterprise.com/api"
    assert core.source == "ingress"

    mcp = cfg.route_for("mcp")
    assert mcp.base_url == "https://api.aqp.enterprise.com/mcp"


def test_unknown_service_raises() -> None:
    cfg = ConnectivityConfig()
    with pytest.raises(ValueError, match="Unknown service"):
        cfg.route_for("nonexistent")


def test_trailing_slash_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_CORE_API_URL", "http://aqp-core:8000/")
    reset_connectivity_config()
    cfg = ConnectivityConfig()
    assert cfg.core_api_url == "http://aqp-core:8000"
