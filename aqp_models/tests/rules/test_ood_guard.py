"""OOD guard verdict tests."""
from __future__ import annotations

import numpy as np

from aqp_models.rules import OODGuard, RangeGuard, RuleRegistry, TensorShapeGuard


def test_ood_guard_allows_in_distribution_features() -> None:
    guard = OODGuard(threshold=3.0)
    rng = np.random.default_rng(seed=0)
    payload = {"features": rng.normal(size=(50, 3))}
    verdict = guard.evaluate(payload=payload)
    assert verdict.allowed is True


def test_ood_guard_blocks_outlier_feature() -> None:
    guard = OODGuard(threshold=2.0)
    features = np.zeros((50, 1))
    features[0, 0] = 1000.0  # massive outlier
    verdict = guard.evaluate(payload={"features": features})
    assert verdict.allowed is False
    assert "zscore" in verdict.reason


def test_range_guard_rejects_out_of_window() -> None:
    guard = RangeGuard(min_value=-1.0, max_value=1.0)
    verdict = guard.evaluate(payload={"features": np.array([[5.0]])})
    assert verdict.allowed is False
    assert "outside" in verdict.reason


def test_tensor_shape_guard_explicit_expected() -> None:
    guard = TensorShapeGuard(expected_n_features=3)
    verdict = guard.evaluate(payload={"features": np.zeros((1, 3))})
    assert verdict.allowed is True
    bad = guard.evaluate(payload={"features": np.zeros((1, 4))})
    assert bad.allowed is False


def test_rule_registry_loads_default_pack() -> None:
    rules = RuleRegistry.load_pack("ood_default")
    assert rules, "ood_default pack should resolve at least one rule"
    # The default pack is the YAML at ``configs/rules/ood_default.yaml``;
    # ensure the registry produced concrete instances rather than entries.
    for r in rules:
        assert hasattr(r, "evaluate")
