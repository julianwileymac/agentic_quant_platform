"""Smoke tests for the Phase 3 unified-client gateway."""
from __future__ import annotations

from typing import Any

import pytest

from aqp.api.client_routes import is_client_mode_enabled


class TestIsClientModeEnabled:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("", False),
            ("false", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("true", True),
            ("True", True),
            ("1", True),
            ("YES", True),
            ("on", True),
        ],
    )
    def test_truthy_values(
        self, monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
    ) -> None:
        monkeypatch.setenv("AQP_CLIENT_MODE", value)
        assert is_client_mode_enabled() is expected

    def test_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AQP_CLIENT_MODE", raising=False)
        assert is_client_mode_enabled() is False


class TestProxyHeaderFiltering:
    def test_hop_by_hop_stripped(self) -> None:
        from aqp.api.proxy import _filter_request_headers

        headers = [
            ("authorization", "Bearer abc"),
            ("content-type", "application/json"),
            ("connection", "keep-alive"),
            ("host", "client.aqp.local"),
            ("content-length", "42"),
            ("transfer-encoding", "chunked"),
            ("upgrade", "h2c"),
            ("X-AQP-Tenant", "org-1"),
        ]
        out = _filter_request_headers(headers)
        assert "authorization" in out
        assert "content-type" in out
        assert "X-AQP-Tenant" in out
        assert "host" not in out
        assert "content-length" not in out
        assert "connection" not in out
        assert "transfer-encoding" not in out
        assert "upgrade" not in out

    def test_response_strips_content_encoding(self) -> None:
        from aqp.api.proxy import _filter_response_headers

        out = _filter_response_headers(
            [
                (b"content-type", b"text/plain"),
                (b"content-encoding", b"gzip"),
                (b"content-length", b"100"),
                (b"x-aqp-cursor", b"abc"),
            ]
        )
        assert "content-type" in out
        assert "x-aqp-cursor" in out
        assert "content-encoding" not in out
        assert "content-length" not in out


class TestWebSocketStructuredReason:
    def test_length_capped_under_120_bytes(self) -> None:
        from aqp.api.ws_proxy import _structured_reason

        reason = _structured_reason(
            service="control_plane",
            detail="upstream_unreachable_after_some_very_long_failure_chain",
            attempt=3,
            max_attempts=3,
        )
        assert len(reason.encode("utf-8")) <= 120

    def test_reason_includes_service_and_detail(self) -> None:
        from aqp.api.ws_proxy import _structured_reason

        reason = _structured_reason(
            service="api",
            detail="x",
            attempt=1,
            max_attempts=3,
        )
        assert "api" in reason
        assert "x" in reason


class TestUpstreamUrl:
    """``_upstream_url`` translates the connectivity service alias to a ws://
    URL. The connectivity alias for the AQP core API is ``core`` (the public
    URL prefix is ``/api``)."""

    def test_http_becomes_ws(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aqp_platform_core.connectivity import reset_connectivity_config

        monkeypatch.setenv("AQP_CORE_API_URL", "http://aqp-core:8000")
        reset_connectivity_config()
        from aqp.api.ws_proxy import _upstream_url

        url = _upstream_url("core", upstream_path="/chat/stream/123")
        assert url == "ws://aqp-core:8000/chat/stream/123"

    def test_https_becomes_wss(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aqp_platform_core.connectivity import reset_connectivity_config

        monkeypatch.setenv("AQP_INGRESS_BASE_URL", "https://api.aqp.enterprise.com")
        reset_connectivity_config()
        from aqp.api.ws_proxy import _upstream_url

        url = _upstream_url("core", upstream_path="/chat/stream/123")
        assert url == "wss://api.aqp.enterprise.com/api/chat/stream/123"

    def test_query_string_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aqp_platform_core.connectivity import reset_connectivity_config

        monkeypatch.setenv("AQP_CORE_API_URL", "http://aqp-core:8000")
        reset_connectivity_config()
        from aqp.api.ws_proxy import _upstream_url

        url = _upstream_url(
            "core",
            upstream_path="/live/stream/cluster",
            query_string="filter=cpu",
        )
        assert url == "ws://aqp-core:8000/live/stream/cluster?filter=cpu"

    def test_unknown_service_alias_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from aqp_platform_core.connectivity import reset_connectivity_config

        reset_connectivity_config()
        from aqp.api.ws_proxy import _upstream_url

        with pytest.raises(ValueError, match="Unknown service"):
            _upstream_url("nonexistent", upstream_path="/x")
