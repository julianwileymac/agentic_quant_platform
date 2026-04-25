"""PyPortfolioOpt-flavored optimizers.

Richer portfolio construction models than the headline
:class:`aqp.strategies.mean_variance.MeanVariancePortfolio` /
:class:`aqp.strategies.hrp.HierarchicalRiskParity` /
:class:`aqp.strategies.risk_parity.RiskParityPortfolio` /
:class:`aqp.strategies.black_litterman.BlackLittermanPortfolio`
trio. Each optimizer here implements
:class:`aqp.core.interfaces.IPortfolioConstructionModel` and plugs into
the same 5-stage framework / backtest runners without any special casing.

Optimizers in this package:

- :class:`EfficientCVaRPortfolio` — conditional value-at-risk tail risk minimisation.
- :class:`EfficientSemivariancePortfolio` — downside deviation minimisation.
- :class:`EfficientCDaRPortfolio` — conditional drawdown at risk.
- :class:`CLAPortfolio` — Markowitz's critical line algorithm.
- :class:`DiscreteAllocation` — helper that rounds target weights to integer
  share quantities given cash + prices.

All rely on ``PyPortfolioOpt`` + ``cvxpy`` (install via the ``portfolio``
extra) and fall back to inverse-volatility when the optimisation fails.
"""
from __future__ import annotations

from aqp.strategies.portfolio_opt.cla import CLAPortfolio
from aqp.strategies.portfolio_opt.discrete_allocation import (
    DiscreteAllocation,
    DiscreteAllocationResult,
)
from aqp.strategies.portfolio_opt.efficient_cdar import EfficientCDaRPortfolio
from aqp.strategies.portfolio_opt.efficient_cvar import EfficientCVaRPortfolio
from aqp.strategies.portfolio_opt.efficient_semivariance import (
    EfficientSemivariancePortfolio,
)
from aqp.strategies.portfolio_opt.min_variance import (
    MarkowitzPortfolio,
    MinVariancePortfolio,
)

__all__ = [
    "CLAPortfolio",
    "DiscreteAllocation",
    "DiscreteAllocationResult",
    "EfficientCDaRPortfolio",
    "EfficientCVaRPortfolio",
    "EfficientSemivariancePortfolio",
    "MarkowitzPortfolio",
    "MinVariancePortfolio",
]
