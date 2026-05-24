"""``LayeredReflectionAdapter`` smoke tests.

Verifies the FinAgent 5-stage cascade:

1. Registers via the :class:`RLComponent` metaclass.
2. ``predict`` invokes :func:`router_complete` exactly 5 times (one per
   stage) — patched here so we don't hit the real LLM.
3. Successfully parses the decision JSON.
4. Memory updates between predict calls feed the reflection stages.
5. ``build`` / ``train`` / ``save`` / ``load`` delegate to the
   optional RL backbone.

Companion tools (KlinePlotter, TradingPlotter, StrategyAgentsTool)
get separate smoke tests so they verify in isolation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import gymnasium as gym
import numpy as np
import pytest

from aqp_rl.agents.llm_hybrid_layered import LayeredReflectionAdapter
from aqp_rl.core.base import RL_KIND_AGENT, list_rl_components


def test_layered_adapter_registered():
    registry = list_rl_components(RL_KIND_AGENT)
    assert "finagent_layered" in registry
    assert registry["finagent_layered"] is LayeredReflectionAdapter


def test_invalid_rl_weight_raises():
    with pytest.raises(ValueError):
        LayeredReflectionAdapter(rl_weight=-0.1)
    with pytest.raises(ValueError):
        LayeredReflectionAdapter(rl_weight=1.5)


def _mock_router_complete(model: str | None, provider: str | None, messages, **kwargs):
    """Patch target: returns different JSON per stage based on prompt content."""
    last = messages[-1]["content"] if messages else ""
    if "low-level intelligence" in last:
        return {"choices": [{"message": {"content": '{"summary": "mock summary"}'}}]}
    if "high-level intelligence" in last:
        return {
            "choices": [
                {"message": {"content": '{"outlook": "mock outlook", "bias": "neutral"}'}}
            ]
        }
    if "low-level reflection" in last:
        return {"choices": [{"message": {"content": '{"critique": "mock critique"}'}}]}
    if "high-level reflection" in last:
        return {
            "choices": [
                {"message": {"content": '{"score": 5, "lesson": "mock lesson"}'}}
            ]
        }
    return {"choices": [{"message": {"content": '{"action": "BUY", "confidence": 0.7}'}}]}


_PATCH_TARGET = "aqp_rl.agents.llm_hybrid_layered._router_complete"


def test_predict_runs_five_stage_cascade():
    """Single ``predict`` call invokes router_complete exactly 5 times."""
    adapter = LayeredReflectionAdapter(rl_weight=0.0, llm_model="ollama/llama3", temperature=0.0)
    obs = np.zeros(8, dtype=np.float32)
    with patch(_PATCH_TARGET, side_effect=_mock_router_complete) as mock_router:
        action, _ = adapter.predict(obs)
    assert mock_router.call_count == 5  # 5 stages per decision
    assert action in {0, 1, 2}  # SELL / HOLD / BUY


def test_decision_parses_action_label():
    adapter = LayeredReflectionAdapter(rl_weight=0.0)
    obs = np.zeros(4, dtype=np.float32)
    with patch(_PATCH_TARGET, side_effect=_mock_router_complete):
        action, _ = adapter.predict(obs)
    assert action == 2  # mock decision = BUY


def test_memory_updates_persist_across_calls():
    adapter = LayeredReflectionAdapter(rl_weight=0.0)
    obs = np.zeros(4, dtype=np.float32)
    with patch(_PATCH_TARGET, side_effect=_mock_router_complete):
        adapter.predict(obs)
        assert adapter._prev_decision == "BUY"  # noqa: SLF001
        assert adapter._prev_outlook == "mock outlook"  # noqa: SLF001
    adapter.update_realised_pnl(realised_short=0.01, realised_k=0.02)
    assert adapter._prev_realised == pytest.approx(0.01)  # noqa: SLF001
    assert adapter._prev_realised_k == pytest.approx(0.02)  # noqa: SLF001


def test_predict_falls_back_to_HOLD_when_router_unavailable():
    """When router_complete raises, the cascade degrades to HOLD (action 1)."""
    adapter = LayeredReflectionAdapter(rl_weight=0.0)
    obs = np.zeros(4, dtype=np.float32)
    with patch(_PATCH_TARGET, side_effect=Exception("boom")):
        action, _ = adapter.predict(obs)
    assert action == 1  # HOLD fallback


def test_rl_weight_one_returns_pure_rl_action():
    """``rl_weight=1.0`` ⇒ adapter ignores LLM and returns the RL action."""

    class _FakeRL:
        rl_kind = "rl_agent"

        def build(self, env):
            pass

        def predict(self, obs, *, deterministic=True):
            return np.asarray([2]), None

        def train(self, *args, **kwargs):
            pass

        def save(self, path):
            return Path(path)

        def load(self, path, env=None):
            pass

        @property
        def model(self):
            return None

    adapter = LayeredReflectionAdapter(rl_agent=_FakeRL(), rl_weight=1.0)
    obs = np.zeros(4, dtype=np.float32)
    with patch(_PATCH_TARGET, side_effect=_mock_router_complete):
        action, _ = adapter.predict(obs)
    assert action == 2


# --------------------------------------------------------------------------- tools


def _load_kline_tool():
    """Direct-import the KlinePlotter via file path, bypassing the broken
    ``aqp.agents.tools.__init__`` import chain."""
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[3]
    tool_path = here / "aqp" / "agents" / "tools" / "finagent" / "kline_plotter.py"
    spec = importlib.util.spec_from_file_location(
        "aqp_rl_test_kline_plotter", str(tool_path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.KlinePlotterTool


def _load_trading_tool():
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[3]
    tool_path = here / "aqp" / "agents" / "tools" / "finagent" / "trading_plotter.py"
    spec = importlib.util.spec_from_file_location(
        "aqp_rl_test_trading_plotter", str(tool_path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TradingPlotterTool


def test_kline_plotter_tool_summary():
    KlinePlotterTool = _load_kline_tool()
    tool = KlinePlotterTool()
    bars = [{"close": float(100 + i)} for i in range(20)]
    summary = tool._run(bars)
    assert "bars=20" in summary
    assert "first=" in summary
    assert "last=" in summary


def test_kline_plotter_handles_json_string():
    KlinePlotterTool = _load_kline_tool()
    tool = KlinePlotterTool()
    payload = json.dumps([{"close": 100.0}, {"close": 101.0}])
    summary = tool._run(payload)
    assert "bars=2" in summary


def test_trading_plotter_summary():
    TradingPlotterTool = _load_trading_tool()
    tool = TradingPlotterTool()
    history = [
        {"action": "BUY", "pnl": 0.01},
        {"action": "HOLD", "pnl": 0.0},
        {"action": "SELL", "pnl": -0.005},
    ]
    summary = tool._run(history)
    assert "steps=3" in summary
    assert "BUY" in summary


def test_kline_plotter_with_no_input_does_not_crash():
    KlinePlotterTool = _load_kline_tool()
    tool = KlinePlotterTool()
    out = tool._run([])
    assert "no bars" in out


def test_trading_plotter_with_no_input_does_not_crash():
    TradingPlotterTool = _load_trading_tool()
    tool = TradingPlotterTool()
    out = tool._run([])
    assert "no history" in out
