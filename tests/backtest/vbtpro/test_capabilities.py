"""Capabilities + ABC contract tests — no optional deps required.

These tests run on every CI configuration because they only inspect the
class-level :attr:`capabilities` attribute and import-time machinery.
"""
from __future__ import annotations

import pytest

from aqp.backtest.base import BaseBacktestEngine, engine_capabilities_index
from aqp.backtest.capabilities import EngineCapabilities


def test_engine_capabilities_dataclass_is_frozen() -> None:
    cap = EngineCapabilities(name="x")
    with pytest.raises(Exception):
        cap.name = "y"  # type: ignore[misc]


def test_engine_capabilities_to_dict_round_trip() -> None:
    cap = EngineCapabilities(name="vbt-pro", supports_signals=True, supports_orders=True)
    payload = cap.to_dict()
    assert payload["name"] == "vbt-pro"
    assert payload["supports_signals"] is True
    assert payload["supports_orders"] is True


def test_engine_capabilities_index_contains_core_engines() -> None:
    idx = engine_capabilities_index()
    # Every always-installed engine must appear; optional ones may not.
    assert "EventDrivenBacktester" in idx
    assert "VectorbtProEngine" in idx
    assert "FallbackBacktestEngine" in idx
    # Capability fields are set sensibly on the event-driven engine.
    event = idx["EventDrivenBacktester"]
    assert event.supports_per_bar_python is True
    assert event.supports_event_driven is True


def test_event_driven_inherits_base() -> None:
    from aqp.backtest.engine import EventDrivenBacktester

    assert issubclass(EventDrivenBacktester, BaseBacktestEngine)


def test_supports_helper() -> None:
    from aqp.backtest.engine import EventDrivenBacktester

    engine = EventDrivenBacktester()
    assert engine.supports("event_driven") is True
    assert engine.supports("event_driven", "per_bar_python") is True
    # Should return False for unknown / unsupported flags.
    assert engine.supports("lob") is False
    assert engine.supports("event_driven", "lob") is False


def test_describe_returns_dict() -> None:
    from aqp.backtest.engine import EventDrivenBacktester

    engine = EventDrivenBacktester()
    payload = engine.describe()
    assert payload["name"] == "event-driven"
    assert payload["license"] == "MIT"
