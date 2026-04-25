"""Strategy framework — Lean-style 5-stage pipeline + reference implementations.

The package re-exports every concrete alpha/portfolio/risk/execution/universe
model so YAML and registered-shortcut resolution just works without needing
to know the exact submodule layout.
"""

import contextlib as _contextlib

# Existing strategies (unchanged).
from aqp.strategies.awesome_oscillator_alpha import AwesomeOscillatorAlpha
from aqp.strategies.base_algo_example import BaseAlgoExample
from aqp.strategies.black_litterman import BlackLittermanPortfolio
from aqp.strategies.bollinger_w_alpha import BollingerWAlpha
from aqp.strategies.drawdown_per_security import MaxDrawdownPerSecurity
from aqp.strategies.dual_thrust_alpha import DualThrustAlpha
from aqp.strategies.ema_cross_alpha import EmaCrossAlphaModel
from aqp.strategies.etf_baskets import (
    LiquidETFUniverse,
    SectorETFUniverse,
    USTreasuriesETFUniverse,
    VolatilityETFUniverse,
)
from aqp.strategies.examples import Sma4Cross, SmaCross, TrailingATRAlpha
from aqp.strategies.execution import MarketOrderExecution
from aqp.strategies.framework import FrameworkAlgorithm
from aqp.strategies.fundamental_universe import FundamentalUniverse
from aqp.strategies.heikin_ashi_alpha import HeikinAshiAlpha
from aqp.strategies.hrp import HierarchicalRiskParity
from aqp.strategies.london_breakout_alpha import LondonBreakoutAlpha
from aqp.strategies.macd_alpha import MacdAlphaModel
from aqp.strategies.mean_reversion import MeanReversionAlpha
from aqp.strategies.mean_variance import MeanVariancePortfolio
from aqp.strategies.momentum import MomentumAlpha
from aqp.strategies.oil_money_alpha import OilMoneyRegressionAlpha
from aqp.strategies.pairs_alpha import PairsTradingAlphaModel
from aqp.strategies.parabolic_sar_alpha import ParabolicSARAlpha
from aqp.strategies.portfolio import EqualWeightPortfolio, SignalWeightedPortfolio
from aqp.strategies.risk_models import BasicRiskModel, NoOpRiskModel
from aqp.strategies.risk_parity import RiskParityPortfolio
from aqp.strategies.rl_policy import RLPolicyAlpha
from aqp.strategies.rsi_alpha import RsiAlphaModel
from aqp.strategies.rsi_pattern_alpha import RsiPatternAlpha
from aqp.strategies.sector_exposure import MaxSectorExposure
from aqp.strategies.shooting_star_alpha import ShootingStarAlpha
from aqp.strategies.trailing_stop import TrailingStopRisk
from aqp.strategies.twap_execution import TwapExecution
from aqp.strategies.universes import StaticUniverse, TopVolumeUniverse
from aqp.strategies.vwap_execution import VwapExecution

# ML alpha models are imported lazily — require xgboost / lightgbm.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.strategies.ml_alphas import (  # noqa: F401
        DeployedModelAlpha,
        GRUAlpha,
        LightGBMAlpha,
        LSTMAlpha,
        TCNAlpha,
        TransformerAlpha,
        XGBoostAlpha,
    )

# FinRL-Trading-style stock-selection alphas (require sklearn, optional xgb/lgbm).
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.strategies.ml_selection import (  # noqa: F401
        MLStockSelectionAlpha,
        SectorNeutralMLAlpha,
    )

# Adaptive rotation strategy + GICS bucket selector.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.strategies.adaptive_rotation import (  # noqa: F401
        AdaptiveRotationAlpha,
        GICSBucketUniverseSelector,
        MarketRegimeClassifier,
    )


# Re-tag legacy portfolio-construction classes under ``kind=portfolio``
# so the registry-driven wizard / taxonomy / Strategy Browser can find
# them alongside the PyPortfolioOpt-backed optimisers.
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.core.registry import _kind_index, tag_class

    _portfolio_index = _kind_index.setdefault("portfolio", {})
    for _cls in (
        EqualWeightPortfolio,
        SignalWeightedPortfolio,
        RiskParityPortfolio,
        MeanVariancePortfolio,
        BlackLittermanPortfolio,
        HierarchicalRiskParity,
    ):
        _portfolio_index.setdefault(_cls.__name__, _cls)
        tag_class(_cls, "kind:portfolio")

# Richer portfolio optimizers from PyPortfolioOpt (cvxpy-backed).
with _contextlib.suppress(Exception):  # pragma: no cover
    from aqp.strategies.portfolio_opt import (  # noqa: F401
        CLAPortfolio,
        DiscreteAllocation,
        DiscreteAllocationResult,
        EfficientCDaRPortfolio,
        EfficientCVaRPortfolio,
        EfficientSemivariancePortfolio,
    )

__all__ = [
    # Alpha (classical TA)
    "AwesomeOscillatorAlpha",
    "BaseAlgoExample",
    "BollingerWAlpha",
    "DualThrustAlpha",
    "EmaCrossAlphaModel",
    "HeikinAshiAlpha",
    "LondonBreakoutAlpha",
    "MacdAlphaModel",
    "MeanReversionAlpha",
    "MomentumAlpha",
    "OilMoneyRegressionAlpha",
    "PairsTradingAlphaModel",
    "ParabolicSARAlpha",
    "DeployedModelAlpha",
    "RLPolicyAlpha",
    "RsiAlphaModel",
    "RsiPatternAlpha",
    "ShootingStarAlpha",
    # Alpha (backtesting.py-style references)
    "Sma4Cross",
    "SmaCross",
    "TrailingATRAlpha",
    # Portfolio
    "BlackLittermanPortfolio",
    "EqualWeightPortfolio",
    "HierarchicalRiskParity",
    "MeanVariancePortfolio",
    "RiskParityPortfolio",
    "SignalWeightedPortfolio",
    # Risk
    "BasicRiskModel",
    "MaxDrawdownPerSecurity",
    "MaxSectorExposure",
    "NoOpRiskModel",
    "TrailingStopRisk",
    # Execution
    "MarketOrderExecution",
    "TwapExecution",
    "VwapExecution",
    # Universe
    "FundamentalUniverse",
    "LiquidETFUniverse",
    "SectorETFUniverse",
    "StaticUniverse",
    "TopVolumeUniverse",
    "USTreasuriesETFUniverse",
    "VolatilityETFUniverse",
    # Framework entry point
    "FrameworkAlgorithm",
]


def list_strategy_tags() -> dict[str, tuple[str, ...]]:
    """Return ``{ClassName: STRATEGY_TAGS}`` for every concrete alpha.

    Used by the Strategy Browser to power tag filters without forcing every
    class to inherit from a tagged base class.
    """
    import importlib
    import inspect

    mod = importlib.import_module(__name__)
    out: dict[str, tuple[str, ...]] = {}
    for name in __all__:
        obj = getattr(mod, name, None)
        if obj is None or not inspect.isclass(obj):
            continue
        tags: tuple[str, ...] | None = None
        for module_name in (getattr(obj, "__module__", ""),):
            try:
                sub = importlib.import_module(module_name)
                tags = tuple(getattr(sub, "STRATEGY_TAGS", ()))
                if tags:
                    break
            except Exception:
                continue
        if tags:
            out[name] = tags
    return out
