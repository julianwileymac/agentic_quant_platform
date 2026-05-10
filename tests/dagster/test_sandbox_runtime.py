"""Sandbox runtime + isolation tests.

Hermetic: doesn't touch real Dagster, real Redis, or real Postgres.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from aqp.cache.client import reset_cache_singleton
from aqp.config import settings
from aqp.dagster.sandbox import (
    SandboxRuntime,
    enter_sandbox_env,
    sandbox_env_active,
)


@pytest.fixture(autouse=True)
def in_memory_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cache_enabled", True)
    monkeypatch.setattr(settings, "cache_redis_url", "redis://nonexistent.local:9999/0")
    reset_cache_singleton()
    yield
    reset_cache_singleton()


def test_sandbox_session_creates_temp_folder() -> None:
    runtime = SandboxRuntime.create_session(owner="alice")
    assert runtime.session.id
    folder = Path(runtime.session.folder)
    assert folder.exists()
    assert folder.is_dir()
    runtime.teardown()
    assert not folder.exists()


def test_write_component_persists_yaml() -> None:
    runtime = SandboxRuntime.create_session(owner="alice")
    target = runtime.write_component("demo", "type: airbyte_connection\n")
    assert target.exists()
    assert "airbyte_connection" in target.read_text(encoding="utf-8")
    assert "demo.yaml" in runtime.session.components
    runtime.teardown()


def test_load_returns_asset_keys_via_fallback() -> None:
    runtime = SandboxRuntime.create_session(owner="alice")
    runtime.write_component("alpha", "type: dummy\n")
    runtime.write_component("beta", "type: dummy\n")
    result = runtime.load()
    assert result["ok"] is True
    keys = [tuple(k) for k in result["asset_keys"]]
    assert ("sandbox", "alpha") in keys
    assert ("sandbox", "beta") in keys
    runtime.teardown()


def test_redis_namespace_isolation() -> None:
    runtime = SandboxRuntime.create_session(owner="alice")
    runtime.namespace.set("foo", "bar")
    assert runtime.namespace.get("foo") == "bar"
    # Production prefix must not leak
    other = runtime.namespace.cache.get_string("aqp:cache:datasets:names")
    assert other is None
    runtime.teardown()
    # After teardown the key is gone
    assert runtime.namespace.get("foo") is None


def test_env_resolver_round_trip() -> None:
    runtime = SandboxRuntime.create_session(owner="alice")
    assert sandbox_env_active() is None
    with enter_sandbox_env(runtime.env):
        active = sandbox_env_active()
        assert active is runtime.env
        assert active.resolve("alpha_vantage_base_url", "https://prod") != "https://prod"
    assert sandbox_env_active() is None
    runtime.teardown()


def test_stream_execute_emits_events() -> None:
    runtime = SandboxRuntime.create_session(owner="alice")
    runtime.write_component("alpha", "type: dummy\n")
    events = list(runtime.stream_execute())
    stages = [event.stage for event in events]
    assert stages[0] == "start"
    assert stages[-1] == "done"
    assert any(stage == "materialize" for stage in stages)
    runtime.teardown()


def test_janitor_drops_expired_sessions() -> None:
    runtime = SandboxRuntime.create_session(owner="alice", ttl_minutes=1)
    runtime.session.expires_at = None  # force-expired by setting None then now
    from datetime import datetime, timedelta
    runtime.session.expires_at = datetime.utcnow() - timedelta(minutes=1)
    dropped = SandboxRuntime.janitor()
    assert runtime.session.id in dropped
