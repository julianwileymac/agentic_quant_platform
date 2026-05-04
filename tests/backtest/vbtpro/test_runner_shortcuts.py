"""Tests for runner shortcut resolution including the new vbt-pro modes."""
from __future__ import annotations

import pytest

from aqp.backtest import runner


def test_primary_shortcut_resolves_to_vbtpro() -> None:
    cfg, label = runner._resolve_backtest_cfg({"engine": "primary", "kwargs": {}})
    assert label == "vectorbt-pro"
    assert cfg["class"] == "VectorbtProEngine"


@pytest.mark.parametrize(
    "shortcut,mode",
    [
        ("vbt-pro:signals", "signals"),
        ("vbt-pro:orders", "orders"),
        ("vbt-pro:optimizer", "optimizer"),
        ("vbt-pro:holding", "holding"),
        ("vbt-pro:random", "random"),
    ],
)
def test_mode_shortcut_injects_mode_kwarg(shortcut: str, mode: str) -> None:
    cfg, label = runner._resolve_backtest_cfg({"engine": shortcut, "kwargs": {}})
    assert label == "vectorbt-pro"
    assert cfg["class"] == "VectorbtProEngine"
    assert cfg["kwargs"]["mode"] == mode


def test_explicit_mode_kwarg_wins_over_shortcut_default() -> None:
    cfg, _ = runner._resolve_backtest_cfg(
        {"engine": "vbt-pro:signals", "kwargs": {"mode": "orders"}}
    )
    assert cfg["kwargs"]["mode"] == "orders"


def test_zvt_and_aat_shortcuts_resolve() -> None:
    zvt_cfg, zvt_label = runner._resolve_backtest_cfg({"engine": "zvt", "kwargs": {}})
    assert zvt_label == "zvt"
    assert zvt_cfg["class"] == "ZvtBacktestEngine"

    aat_cfg, aat_label = runner._resolve_backtest_cfg({"engine": "aat", "kwargs": {}})
    assert aat_label == "aat"
    assert aat_cfg["class"] == "AatBacktestEngine"


def test_legacy_vectorbtpro_module_path_still_works() -> None:
    from aqp.backtest.vectorbtpro_engine import VectorbtProEngine as Legacy
    from aqp.backtest.vbtpro.engine import VectorbtProEngine as Canonical

    assert Legacy is Canonical
