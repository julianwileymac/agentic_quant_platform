"""Canonical Pydantic / dataclass types for trading agents.

These types are emitted by the analyst / debate / trader / risk / portfolio
manager roles and consumed by :class:`aqp.strategies.agentic.agentic_alpha.AgenticAlpha`,
the persistence layer, and the UI. Keep them deterministic and
JSON-serializable so they survive the cache round trip and fit cleanly
in the SQLAlchemy ``JSON`` columns.

Design notes:

- We use **Pydantic models** rather than dataclasses so CrewAI's tool
  schema + the REST surface get automatic validation and JSON Schema.
- ``TraderAction`` is deliberately ``BUY / SELL / HOLD`` (TradingAgents
  terminology) rather than the platform's ``Direction.LONG/SHORT`` — the
  adapter to :class:`aqp.core.types.Signal` lives in the
  :class:`AgenticAlpha`.
- ``Rating5`` mirrors TradingAgents' five-tier scale.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Rating5(StrEnum):
    """Five-tier rating scale (TradingAgents compatible)."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"

    @classmethod
    def numeric(cls, rating: "Rating5 | str") -> int:
        """Return a signed integer in ``{-2, -1, 0, 1, 2}`` for the rating."""
        r = rating if isinstance(rating, cls) else parse_rating(str(rating))
        return {
            cls.STRONG_SELL: -2,
            cls.SELL: -1,
            cls.HOLD: 0,
            cls.BUY: 1,
            cls.STRONG_BUY: 2,
        }[r]


def parse_rating(raw: str | None) -> Rating5:
    """Best-effort parse that tolerates "Buy", "BUY", "strong buy", etc."""
    if raw is None:
        return Rating5.HOLD
    cleaned = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if not cleaned:
        return Rating5.HOLD
    for r in Rating5:
        if cleaned == r.value:
            return r
    # Heuristic fallbacks commonly produced by LLMs.
    if cleaned in {"positive", "bull", "bullish"}:
        return Rating5.BUY
    if cleaned in {"negative", "bear", "bearish"}:
        return Rating5.SELL
    if cleaned in {"neutral", "flat"}:
        return Rating5.HOLD
    if cleaned.startswith("strong_b") or cleaned.startswith("strongbuy"):
        return Rating5.STRONG_BUY
    if cleaned.startswith("strong_s") or cleaned.startswith("strongsell"):
        return Rating5.STRONG_SELL
    return Rating5.HOLD


class TraderAction(StrEnum):
    """Discrete action emitted by the Trader / Portfolio Manager roles."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

    @classmethod
    def from_rating(cls, rating: Rating5 | str) -> "TraderAction":
        """Derive an action from a rating using the TradingAgents convention."""
        r = rating if isinstance(rating, Rating5) else parse_rating(str(rating))
        if r in (Rating5.STRONG_BUY, Rating5.BUY):
            return cls.BUY
        if r in (Rating5.STRONG_SELL, Rating5.SELL):
            return cls.SELL
        return cls.HOLD


class AnalystReport(BaseModel):
    """Structured output from any analyst role (fundamentals/news/sentiment/technical)."""

    role: str = Field(description="Name of the producing role, e.g. 'fundamentals_analyst'")
    summary: str = Field(description="One-paragraph analyst view")
    evidence: list[str] = Field(
        default_factory=list,
        description="Bullet evidence strings (ideally with pointers to sources)",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Self-reported confidence in [0, 1]",
    )
    rating: Rating5 = Field(default=Rating5.HOLD)

    @field_validator("rating", mode="before")
    @classmethod
    def _coerce_rating(cls, v: Any) -> Rating5:
        return parse_rating(str(v)) if not isinstance(v, Rating5) else v


class DebateTurn(BaseModel):
    """One utterance in the Bull vs Bear researcher debate."""

    round: int = Field(ge=0)
    side: str = Field(description="'bull' or 'bear'")
    argument: str
    cites: list[str] = Field(default_factory=list)
    token_cost_usd: float = 0.0


class TraderPlan(BaseModel):
    """The Trader role's proposed action before risk review."""

    symbol: str = Field(description="vt_symbol (e.g. AAPL.NASDAQ)")
    proposed_action: TraderAction
    size_pct: float = Field(
        ge=0.0,
        le=1.0,
        description="Target position size as a fraction of portfolio equity",
    )
    horizon_days: int = Field(default=5, ge=1)
    rationale: str = ""

    @field_validator("proposed_action", mode="before")
    @classmethod
    def _coerce_action(cls, v: Any) -> TraderAction:
        if isinstance(v, TraderAction):
            return v
        s = str(v).upper().strip()
        if s in {"BUY", "LONG"}:
            return TraderAction.BUY
        if s in {"SELL", "SHORT"}:
            return TraderAction.SELL
        return TraderAction.HOLD


class RiskVerdict(BaseModel):
    """Risk Manager review of a :class:`TraderPlan`."""

    approved: bool = True
    adjusted_size_pct: float | None = None
    reasons: list[str] = Field(default_factory=list)


class PortfolioDecision(BaseModel):
    """Portfolio Manager's final say — the output of the trader crew."""

    symbol: str
    action: TraderAction = TraderAction.HOLD
    size_pct: float = 0.0
    confidence: float = 0.5
    rating: Rating5 = Rating5.HOLD
    rationale: str = ""


class AgentDecision(BaseModel):
    """Canonical per-``(symbol, timestamp)`` decision payload.

    Written to :class:`aqp.agents.trading.decision_cache.DecisionCache` and
    persisted as one row in the ``agent_decisions`` table. Consumed by
    :class:`aqp.strategies.agentic.agentic_alpha.AgenticAlpha`.
    """

    vt_symbol: str = Field(description="Canonical vt_symbol")
    timestamp: datetime
    action: TraderAction = TraderAction.HOLD
    size_pct: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    rating: Rating5 = Rating5.HOLD
    rationale: str = ""
    evidence: list[str] = Field(default_factory=list)

    # Traceability
    crew_run_id: str | None = None
    provider: str = ""
    deep_model: str = ""
    quick_model: str = ""
    token_cost_usd: float = 0.0
    context_hash: str = ""
    analyst_reports: list[AnalystReport] = Field(default_factory=list)
    debate_turns: list[DebateTurn] = Field(default_factory=list)
    trader_plan: TraderPlan | None = None
    risk_verdict: RiskVerdict | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (datetimes converted to ISO)."""
        return self.model_dump(mode="json")

    @classmethod
    def hold(
        cls,
        vt_symbol: str,
        timestamp: datetime,
        *,
        rationale: str = "No actionable signal.",
    ) -> "AgentDecision":
        """Convenience: produce a neutral ``HOLD`` decision."""
        return cls(
            vt_symbol=vt_symbol,
            timestamp=timestamp,
            action=TraderAction.HOLD,
            size_pct=0.0,
            confidence=0.5,
            rating=Rating5.HOLD,
            rationale=rationale,
        )
