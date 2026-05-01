from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.core.types import PortfolioTarget, Symbol
from aqp.strategies.risk_models import NoOpRiskModel, TVaRInterceptor


def test_tvar_formula_matches_expected_normal_closed_form() -> None:
    tvar = TVaRInterceptor.tvar_normal(mu=0.0, sigma=0.02, alpha=0.95)

    assert abs(tvar - 0.041254) < 1e-5


def test_tvar_interceptor_flattens_targets_above_limit() -> None:
    symbol = Symbol.parse("SPY.NASDAQ")
    np.random.seed(7)
    history = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=40),
            "vt_symbol": "SPY.NASDAQ",
            "close": 100 * np.exp(np.random.normal(0.0, 0.02, 40).cumsum()),
        }
    )
    model = TVaRInterceptor(
        NoOpRiskModel(),
        alpha=0.95,
        max_tvar=0.001,
        lookback_days=30,
    )

    targets = model.evaluate(
        [PortfolioTarget(symbol=symbol, target_weight=1.0)],
        {"history": history},
    )

    assert targets[0].target_weight == 0.0
    assert "tvar" in (targets[0].rationale or "")
