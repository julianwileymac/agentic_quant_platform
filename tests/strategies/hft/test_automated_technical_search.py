"""Tests for the automated technical strategy search + bootstrap baseline."""
from __future__ import annotations

from datetime import datetime

import numpy as np

from aqp.strategies.hft.automated_technical_search import (
    BootstrapTechSearchAlpha,
    TechnicalRule,
    bootstrap_baseline,
    evaluate_rule,
    search_rules,
)
from aqp.strategies.lob import LobState


def _make_trending_prices(n: int = 500, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    drift = 0.001
    noise = rng.normal(0.0, 0.01, size=n)
    return np.cumsum(np.full(n, drift) + noise) + 100.0


def _make_random_prices(n: int = 500, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(0.0, 0.01, size=n)) + 100.0


def test_registry_entry() -> None:
    from aqp.core.registry import resolve

    assert resolve("BootstrapTechSearchAlpha") is BootstrapTechSearchAlpha


def test_evaluate_rule_returns_finite_sharpe() -> None:
    prices = _make_trending_prices()
    rule = TechnicalRule(name="ma_10_50", fast=10, slow=50, threshold=0.0)
    result = evaluate_rule(prices, rule)
    assert "sharpe" in result
    assert np.isfinite(result["sharpe"])
    assert result["trades"] >= 0


def test_bootstrap_baseline_size_matches_n_trials() -> None:
    prices = _make_random_prices()
    rule = TechnicalRule(name="ma_5_20", fast=5, slow=20, threshold=0.0)
    baseline = bootstrap_baseline(prices, rule=rule, n_trials=32)
    assert baseline.shape == (32,)
    assert np.all(np.isfinite(baseline))


def test_search_rules_marks_survivors_on_trending_path() -> None:
    prices = _make_trending_prices(n=300, seed=7)
    out = search_rules(
        prices,
        rule_space=[
            TechnicalRule(name="ma_5_50", fast=5, slow=50, threshold=0.0),
            TechnicalRule(name="ma_10_100", fast=10, slow=100, threshold=0.0),
        ],
        n_trials=24,
        significance=0.5,  # lenient so the test is not flaky
        seed=11,
    )
    assert len(out) == 2
    assert all("survives" in row for row in out)


def test_alpha_with_empty_rules_is_noop() -> None:
    alpha = BootstrapTechSearchAlpha(rules=[])
    state = LobState(
        timestamp=datetime(2024, 1, 1),
        asset_no=0,
        best_bid=100.0,
        best_ask=100.1,
        bid_qty=10.0,
        ask_qty=10.0,
        position=0.0,
        cash=0.0,
    )
    assert alpha.on_event(state) == []


def test_alpha_emits_long_under_persistent_upward_drift() -> None:
    rules = [
        TechnicalRule(name="ma_3_10", fast=3, slow=10, threshold=0.0),
        TechnicalRule(name="ma_5_20", fast=5, slow=20, threshold=0.0),
    ]
    alpha = BootstrapTechSearchAlpha(rules=rules, order_size=2.0, max_position=10.0)
    # Push a strictly increasing price series through the strategy.
    intents: list = []
    for i in range(40):
        price = 100.0 + 0.1 * i
        state = LobState(
            timestamp=datetime(2024, 1, 1),
            asset_no=0,
            best_bid=price,
            best_ask=price + 0.01,
            bid_qty=5.0,
            ask_qty=5.0,
            position=0.0,
            cash=0.0,
        )
        intents.extend(alpha.on_event(state))
    assert any(i.side == "buy" for i in intents)


def test_alpha_emits_short_under_persistent_downward_drift() -> None:
    rules = [TechnicalRule(name="ma_3_10", fast=3, slow=10, threshold=0.0)]
    alpha = BootstrapTechSearchAlpha(rules=rules, order_size=1.0, max_position=10.0)
    intents: list = []
    for i in range(40):
        price = 100.0 - 0.1 * i
        state = LobState(
            timestamp=datetime(2024, 1, 1),
            asset_no=0,
            best_bid=price,
            best_ask=price + 0.01,
            bid_qty=5.0,
            ask_qty=5.0,
            position=0.0,
            cash=0.0,
        )
        intents.extend(alpha.on_event(state))
    assert any(i.side == "sell" for i in intents)
