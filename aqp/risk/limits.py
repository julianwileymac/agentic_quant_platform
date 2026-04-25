"""Risk limit dataclasses."""
from __future__ import annotations

from dataclasses import dataclass

from aqp.config import settings


@dataclass
class RiskLimits:
    max_position_pct: float = settings.risk_max_position_pct
    max_daily_loss_pct: float = settings.risk_max_daily_loss_pct
    max_drawdown_pct: float = settings.risk_max_drawdown_pct
    max_concentration_pct: float = 0.50
    max_gross_exposure: float = 1.0


@dataclass
class LimitBreach:
    kind: str
    message: str
    value: float
    limit: float
    severity: str = "warning"
