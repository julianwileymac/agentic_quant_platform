from __future__ import annotations

from aqp.core.types import Direction, PortfolioTarget, PositionData, Symbol
from aqp.strategies.risk_models import TrailingStopRiskManagementModel


def test_trailing_stop_emits_zero_weight_override() -> None:
    symbol = Symbol.parse("SPY.NASDAQ")
    pos = PositionData(
        symbol=symbol,
        direction=Direction.LONG,
        quantity=10,
        average_price=100.0,
    )
    model = TrailingStopRiskManagementModel(max_drawdown_percent=0.05)

    first = model.evaluate(
        [PortfolioTarget(symbol=symbol, target_weight=0.5)],
        {"positions": {"SPY.NASDAQ": pos}, "prices": {"SPY.NASDAQ": 110.0}},
    )
    assert first[0].target_weight == 0.5

    stopped = model.evaluate(
        [PortfolioTarget(symbol=symbol, target_weight=0.5)],
        {"positions": {"SPY.NASDAQ": pos}, "prices": {"SPY.NASDAQ": 108.0}},
    )

    assert len(stopped) == 1
    assert stopped[0].symbol == symbol
    assert stopped[0].target_weight == 0.0
    assert "trailing_stop" in (stopped[0].rationale or "")
