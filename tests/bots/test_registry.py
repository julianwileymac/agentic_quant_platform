"""Registry behaviour: code-driven add, lookup, YAML scan, decorator."""
from __future__ import annotations

from pathlib import Path

import pytest

from aqp.bots import registry as bot_registry
from aqp.bots.registry import (
    add_spec,
    get_bot_spec,
    list_bot_specs,
    register_bot_spec,
    reload_yaml_dir,
)
from aqp.bots.spec import BotSpec, UniverseRef


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch):
    """Reset the in-memory registry between tests."""
    fresh: dict = {}
    scanned: set = set()
    monkeypatch.setattr(bot_registry, "_REGISTRY", fresh, raising=False)
    monkeypatch.setattr(bot_registry, "_DIR_SCANNED", scanned, raising=False)
    yield
    fresh.clear()
    scanned.clear()


def _make_spec(name: str = "Test Bot") -> BotSpec:
    return BotSpec(
        name=name,
        kind="trading",
        universe=UniverseRef(symbols=["AAPL.NASDAQ"]),
        strategy={"class": "FrameworkAlgorithm", "kwargs": {}},
        backtest={"engine": "vbt-pro:signals", "kwargs": {}},
    )


def test_add_spec_then_get(monkeypatch) -> None:
    monkeypatch.setattr(
        bot_registry, "_DEFAULT_DIR", Path("/nonexistent/configs/bots"), raising=False
    )
    spec = _make_spec("Adder")
    add_spec(spec)
    fetched = get_bot_spec("Adder")
    assert fetched.snapshot_hash() == spec.snapshot_hash()


def test_get_unknown_raises(monkeypatch) -> None:
    monkeypatch.setattr(
        bot_registry, "_DEFAULT_DIR", Path("/nonexistent/configs/bots"), raising=False
    )
    with pytest.raises(KeyError):
        get_bot_spec("definitely-not-registered")


def test_register_decorator_adds_spec(monkeypatch) -> None:
    monkeypatch.setattr(
        bot_registry, "_DEFAULT_DIR", Path("/nonexistent/configs/bots"), raising=False
    )

    @register_bot_spec("Decorated")
    def make() -> BotSpec:
        return _make_spec("Decorated")

    assert get_bot_spec("Decorated").name == "Decorated"


def test_register_decorator_rejects_non_spec(monkeypatch) -> None:
    monkeypatch.setattr(
        bot_registry, "_DEFAULT_DIR", Path("/nonexistent/configs/bots"), raising=False
    )

    with pytest.raises(TypeError):

        @register_bot_spec("WrongType")
        def make() -> dict:
            return {"not": "a spec"}


def test_yaml_scan_loads_directory(tmp_path: Path, monkeypatch) -> None:
    sub = tmp_path / "trading"
    sub.mkdir()
    spec = _make_spec("YamlTrader")
    (sub / "trader.yaml").write_text(spec.to_yaml(), encoding="utf-8")
    monkeypatch.setattr(bot_registry, "_DEFAULT_DIR", tmp_path, raising=False)

    specs = list_bot_specs()
    assert any(s.name == "YamlTrader" for s in specs)


def test_reload_yaml_dir_replaces_existing(tmp_path: Path, monkeypatch) -> None:
    sub = tmp_path / "trading"
    sub.mkdir()
    spec = _make_spec("Reloadable")
    spec.description = "v1"
    (sub / "reload.yaml").write_text(spec.to_yaml(), encoding="utf-8")
    monkeypatch.setattr(bot_registry, "_DEFAULT_DIR", tmp_path, raising=False)

    n = reload_yaml_dir(tmp_path)
    assert n >= 1
    assert get_bot_spec("Reloadable").description == "v1"

    spec.description = "v2"
    (sub / "reload.yaml").write_text(spec.to_yaml(), encoding="utf-8")
    reload_yaml_dir(tmp_path)
    assert get_bot_spec("Reloadable").description == "v2"
