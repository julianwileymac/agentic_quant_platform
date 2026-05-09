"""Cross-session strategy parameter memory keyed by regime.

AgentQuant's killer feature is its SQLite-backed strategy memory:
when the agent backtests a strategy under regime X and finds a Sharpe
> threshold, it stores ``(strategy_id, regime, params, sharpe)`` so a
later session running under regime X can warm-start with those params
instead of regenerating hypotheses from scratch.

We mirror that pattern on Postgres with workspace-scoped rows so each
tenant builds up its own knowledge base. Hot reads are also
opportunistically cached in Redis (``strategy:regime:<key>``) by
:func:`get_best_params` to avoid SQL round-trips inside the hot
optimisation loop.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from aqp.persistence._tenancy_mixins import ProjectScopedMixin
from aqp.persistence.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class StrategyRegimeMemory(Base, ProjectScopedMixin):
    """Best-known parameters for ``(strategy, regime)`` per workspace.

    Keys:

    - :attr:`strategy_id` — the strategy class registry name (e.g.
      ``BBadXMacDrSi``). String rather than FK so the row survives a
      strategy re-rev.
    - :attr:`regime` — the canonical regime label
      (:class:`aqp.data.regime.Regime`'s string value).
    - :attr:`workspace_id` / :attr:`owner_user_id` (via mixin) — every
      tenant builds up its own memory; cross-workspace sharing is an
      explicit promotion, never an implicit leak.

    Rows are immutable per ``(strategy_id, regime, params_hash)`` —
    re-fitting with new params writes a new row, and
    :func:`get_best_params` picks the highest sharpe.
    """

    __tablename__ = "strategy_regime_memory"
    id = Column(String(36), primary_key=True, default=_uuid)
    strategy_id = Column(String(160), nullable=False, index=True)
    regime = Column(String(64), nullable=False, index=True)
    params_hash = Column(String(64), nullable=False)
    params = Column(JSON, default=dict)
    best_sharpe = Column(Float, nullable=True)
    best_sortino = Column(Float, nullable=True)
    best_calmar = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    n_observations = Column(Integer, nullable=False, default=1)
    backtest_run_id = Column(String(36), nullable=True, index=True)
    notes = Column(JSON, default=dict)
    first_observed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_observed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "strategy_id", "regime", "params_hash",
            name="uq_strategy_regime_memory_ws_strategy_regime_hash",
        ),
        Index(
            "ix_strategy_regime_memory_lookup",
            "workspace_id", "strategy_id", "regime", "best_sharpe",
        ),
    )


__all__ = ["StrategyRegimeMemory"]
