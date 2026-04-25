"""Deployment-backed alpha integration tests."""
from __future__ import annotations

import pandas as pd

from aqp.core.types import Direction, Symbol
from aqp.strategies.ml_alphas import DeployedModelAlpha


class _FakeModel:
    def predict(self, dataset, segment: str = "infer") -> pd.Series:  # noqa: ARG002
        idx = pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2023-12-28"), "AAA.NASDAQ"),
                (pd.Timestamp("2023-12-28"), "BBB.NASDAQ"),
            ],
            names=["datetime", "vt_symbol"],
        )
        return pd.Series([0.02, -0.03], index=idx, name="score")


def test_deployed_alpha_emits_signals_from_dataset_predictions(
    synthetic_bars: pd.DataFrame,
    monkeypatch,
) -> None:
    alpha = DeployedModelAlpha(deployment_id="dep-test")
    alpha._loaded = True
    alpha._model = _FakeModel()
    alpha._dataset_cfg = {
        "class": "DatasetH",
        "module_path": "aqp.ml.dataset",
        "kwargs": {
            "handler": {"class": "Alpha158", "module_path": "aqp.ml.features.alpha158", "kwargs": {}},
            "segments": {"infer": ["2023-01-01", "2023-12-31"]},
        },
    }

    monkeypatch.setattr("aqp.core.registry.build_from_config", lambda cfg: object())

    bars = synthetic_bars[
        synthetic_bars["vt_symbol"].isin(["AAA.NASDAQ", "BBB.NASDAQ"])
    ].copy()
    universe = [Symbol.parse("AAA.NASDAQ"), Symbol.parse("BBB.NASDAQ")]
    signals = alpha.generate_signals(
        bars=bars,
        universe=universe,
        context={"current_time": pd.Timestamp("2023-12-29")},
    )
    assert len(signals) == 2
    dirs = {signal.symbol.vt_symbol: signal.direction for signal in signals}
    assert dirs["AAA.NASDAQ"] == Direction.LONG
    assert dirs["BBB.NASDAQ"] == Direction.SHORT
