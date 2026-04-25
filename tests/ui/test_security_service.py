"""Tests for UI security-service error translation helpers."""
from __future__ import annotations

from typing import Any

import httpx

from aqp.ui.services import security as sec


def _status_error(path: str, status: int, body: Any) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", f"http://localhost:8000{path}")
    resp = httpx.Response(status_code=status, json=body, request=req)
    return httpx.HTTPStatusError(
        f"{status} error",
        request=req,
        response=resp,
    )


def test_get_ibkr_availability_success(monkeypatch) -> None:
    monkeypatch.setattr(
        sec,
        "api_get",
        lambda path, params=None: {"ok": True, "message": "ready", "host": "127.0.0.1", "port": 7497},
    )
    out = sec.get_ibkr_availability(refresh=True)
    assert out.ok is True
    assert out.message == "ready"
    assert out.host == "127.0.0.1"
    assert out.port == 7497


def test_get_ibkr_availability_maps_request_error(monkeypatch) -> None:
    def _raise(path, params=None):
        req = httpx.Request("GET", f"http://localhost:8000{path}")
        raise httpx.ConnectError("connect failed", request=req)

    monkeypatch.setattr(sec, "api_get", _raise)
    out = sec.get_ibkr_availability()
    assert out.ok is False
    assert out.message == "API unreachable"


def test_get_ibkr_availability_preserves_http_status_detail(monkeypatch) -> None:
    def _raise(path, params=None):
        raise _status_error(
            path,
            503,
            {"detail": {"detail": "IBKR probe failed", "code": "ibkr_unavailable"}},
        )

    monkeypatch.setattr(sec, "api_get", _raise)
    out = sec.get_ibkr_availability()
    assert out.ok is False
    assert out.message == "HTTP 503: IBKR probe failed"


def test_get_ibkr_availability_404_falls_back_to_brokers_status(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_get(path, params=None):
        calls.append(path)
        if path == "/data/ibkr/historical/availability":
            raise _status_error(path, 404, {"detail": "Not Found"})
        if path == "/brokers/ibkr/status":
            return {
                "ok": False,
                "error": "No process listening on 127.0.0.1:7497.",
                "endpoint": "127.0.0.1:7497",
                "stage": "gateway-down",
            }
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(sec, "api_get", _fake_get)
    out = sec.get_ibkr_availability()
    assert out.ok is False
    assert out.message == "No process listening on 127.0.0.1:7497."
    assert out.host == "127.0.0.1"
    assert out.port == 7497
    assert calls == ["/data/ibkr/historical/availability", "/brokers/ibkr/status"]
