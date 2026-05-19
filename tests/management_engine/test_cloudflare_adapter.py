"""Tests for `aqp.cloudflare.CloudflareEdgeAdapter`.

The adapter is purely a thin wrapper around the Cloudflare Python
SDK — we stub the SDK with a fake client + verify the adapter's
shape (correct method names, ingress catch-all appended,
summaries materialised).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from aqp.cloudflare.adapter import (
    CloudflareAdapterError,
    CloudflareEdgeAdapter,
    TunnelSummary,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeTunnel:
    id: str
    name: str
    status: str = "healthy"
    config_src: str = "cloudflare"
    created_at: str = "2026-05-18T00:00:00Z"
    connections: list[dict[str, Any]] | None = None


class _FakeTunnels:
    def __init__(self) -> None:
        self._tunnels: list[_FakeTunnel] = []

    def list(self, *, account_id: str, name: str | None = None) -> list[_FakeTunnel]:
        if name:
            return [t for t in self._tunnels if t.name == name]
        return list(self._tunnels)

    def create(self, *, account_id: str, name: str, config_src: str = "cloudflare") -> _FakeTunnel:
        t = _FakeTunnel(id=f"id-{name}", name=name, config_src=config_src)
        self._tunnels.append(t)
        return t

    def delete(self, *, tunnel_id: str, account_id: str) -> None:
        self._tunnels = [t for t in self._tunnels if t.id != tunnel_id]


class _FakeConfigurations:
    def __init__(self) -> None:
        self.last_config: dict[str, Any] | None = None

    def get(self, *, tunnel_id: str, account_id: str) -> Any:
        return type("Cfg", (), {"config": self.last_config or {}})()

    def update(self, *, tunnel_id: str, account_id: str, config: dict[str, Any]) -> None:
        self.last_config = config


class _FakeCloudflared:
    def __init__(self) -> None:
        self.configurations = _FakeConfigurations()


class _FakeZeroTrust:
    def __init__(self) -> None:
        self.tunnels = _FakeTunnels()
        self.tunnels.cloudflared = _FakeCloudflared()  # type: ignore[attr-defined]
        self.access = type("A", (), {"applications": type("P", (), {
            "list": lambda *, account_id: [],
            "create": lambda *, account_id, **kwargs: type("App", (), {
                **kwargs,
                "id": "app-1",
                "name": kwargs.get("name", ""),
                "domain": kwargs.get("domain", ""),
                "type": kwargs.get("type", "self_hosted"),
                "aud": "aud-1",
                "session_duration": kwargs.get("session_duration", "24h"),
                "auto_redirect_to_identity": kwargs.get("auto_redirect_to_identity", False),
            })(),
            "update": lambda *, app_id, account_id, **kwargs: type("App", (), {
                **kwargs,
                "id": app_id,
                "name": kwargs.get("name", ""),
                "domain": kwargs.get("domain", ""),
                "type": kwargs.get("type", "self_hosted"),
                "aud": "aud-1",
                "session_duration": kwargs.get("session_duration", "24h"),
                "auto_redirect_to_identity": kwargs.get("auto_redirect_to_identity", False),
            })(),
        })()})()


class _FakeUser:
    class tokens:
        @staticmethod
        def verify():
            return type("V", (), {"id": "tok-1", "status": "active"})()


class _FakeSDK:
    def __init__(self) -> None:
        self.zero_trust = _FakeZeroTrust()
        self.user = _FakeUser()
        self.dns = type("D", (), {"records": type("R", (), {
            "list": lambda *, zone_id, name=None: [],
            "create": lambda *, zone_id, **kwargs: type("Rec", (), {
                **kwargs,
                "id": "rec-1",
                "zone_id": zone_id,
            })(),
            "update": lambda *, dns_record_id, zone_id, **kwargs: type("Rec", (), {
                **kwargs,
                "id": dns_record_id,
                "zone_id": zone_id,
            })(),
            "delete": lambda *, dns_record_id, zone_id: None,
        })()})()


@dataclass
class _FakeClient:
    account_id: str = "acct-1"
    sdk: Any = None

    def __post_init__(self) -> None:
        if self.sdk is None:
            self.sdk = _FakeSDK()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_ok() -> None:
    client = _FakeClient()
    adapter = CloudflareEdgeAdapter(client=client)
    h = adapter.health()
    assert h["status"] == "ok"
    assert h["account_id"] == "acct-1"
    assert h["token_id"] == "tok-1"


def test_create_and_list_tunnel_round_trip() -> None:
    client = _FakeClient()
    adapter = CloudflareEdgeAdapter(client=client)
    created = adapter.create_tunnel(name="my-tunnel")
    assert isinstance(created, TunnelSummary)
    assert created.id == "id-my-tunnel"
    assert created.name == "my-tunnel"
    tunnels = adapter.list_tunnels()
    assert any(t.name == "my-tunnel" for t in tunnels)


def test_put_tunnel_config_appends_catch_all() -> None:
    client = _FakeClient()
    adapter = CloudflareEdgeAdapter(client=client)
    adapter.create_tunnel(name="t1")
    adapter.put_tunnel_config(
        tunnel_id="id-t1",
        ingress=[{"hostname": "a.example.com", "service": "http://a:80"}],
    )
    cfg = client.sdk.zero_trust.tunnels.cloudflared.configurations.last_config
    assert cfg is not None
    # Must end with a catch-all even if the caller didn't add one.
    assert cfg["ingress"][-1] == {"service": "http_status:404"}
    assert cfg["ingress"][0] == {
        "hostname": "a.example.com",
        "service": "http://a:80",
    }


def test_delete_tunnel_returns_dict() -> None:
    client = _FakeClient()
    adapter = CloudflareEdgeAdapter(client=client)
    adapter.create_tunnel(name="z")
    out = adapter.delete_tunnel(tunnel_id="id-z")
    assert out == {"tunnel_id": "id-z", "deleted": True}


def test_adapter_translates_sdk_errors() -> None:
    class _Boom:
        @staticmethod
        def list(*, account_id, name=None):
            raise RuntimeError("upstream borked")

    class _SDK(_FakeSDK):
        def __init__(self) -> None:
            super().__init__()
            self.zero_trust.tunnels = _Boom()  # type: ignore[assignment]

    adapter = CloudflareEdgeAdapter(client=_FakeClient(sdk=_SDK()))
    with pytest.raises(CloudflareAdapterError):
        adapter.list_tunnels()
