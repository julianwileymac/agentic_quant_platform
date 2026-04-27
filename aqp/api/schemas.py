"""Pydantic request/response schemas for the REST API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    redis: bool
    postgres: bool
    chromadb: bool
    vllm: bool = False
    models: list[str] = Field(default_factory=list)
    vllm_models: list[str] = Field(default_factory=list)


class TaskAccepted(BaseModel):
    task_id: str
    status: str = "queued"
    stream_url: str | None = None


class ChatContext(BaseModel):
    """Optional ambient context the webui passes with every chat call.

    The fields mirror the route a user is currently on so the assistant
    can answer questions like "summarize this backtest" or "what's the
    last close for this symbol" without the user repeating themselves.
    """

    page: str | None = None
    vt_symbol: str | None = None
    backtest_id: str | None = None
    strategy_id: str | None = None
    paper_run_id: str | None = None
    ml_model_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    tier: str = Field(default="quick", description="quick | deep")
    context: ChatContext | None = None


class ChatResponse(BaseModel):
    session_id: str | None
    content: str
    model: str
    tokens: dict[str, int] = Field(default_factory=dict)
    task_id: str | None = None


class ChatThreadSummary(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime
    closed_at: datetime | None = None
    message_count: int = 0


class ChatThreadCreate(BaseModel):
    title: str | None = None


class CrewRunRequest(BaseModel):
    prompt: str
    session_id: str | None = None
    config_path: str | None = None


class BacktestRequest(BaseModel):
    config: dict[str, Any]
    run_name: str = "adhoc"


class WalkForwardRequest(BaseModel):
    config: dict[str, Any]
    train_window_days: int = 252
    test_window_days: int = 63
    step_days: int = 63


class MonteCarloRequest(BaseModel):
    backtest_id: str
    n_runs: int = 500
    method: str = "bootstrap"


class TrainRLRequest(BaseModel):
    config: dict[str, Any]
    run_name: str | None = None


class AgenticPrecomputeRequest(BaseModel):
    """Populate the decision cache for ``(symbols × dates)``.

    Used by the Quickstart Wizard and by power users who want to reuse a
    cached crew run across multiple strategy configs.
    """

    strategy_id: str
    symbols: list[str]
    start: str
    end: str
    preset: str = "trader_crew_quick"
    rebalance_frequency: str = "weekly"
    overrides: dict[str, Any] = Field(default_factory=dict)


class AgenticBacktestRequest(BaseModel):
    """One-shot: precompute + backtest + persist sidecar."""

    symbols: list[str]
    start: str
    end: str
    strategy_id: str | None = None
    run_name: str = "agentic-adhoc"
    preset: str = "trader_crew_quick"
    provider: str = ""
    deep_model: str = ""
    quick_model: str = ""
    max_debate_rounds: int | None = None
    rebalance_frequency: str = "weekly"
    mode: str = "precompute"
    skip_precompute: bool = False
    # Optional override for the framework config. When omitted the server
    # uses ``configs/strategies/agentic_trader_quickstart.yaml``.
    config: dict[str, Any] | None = None


class AgenticPipelineRequest(BaseModel):
    """Multi-run orchestration request for agentic backtests."""

    symbols: list[str]
    start: str
    end: str
    strategy_id: str | None = None
    run_name: str = "agentic-pipeline"
    preset: str = "trader_crew_quick"
    provider: str = ""
    deep_model: str = ""
    quick_model: str = ""
    max_debate_rounds: int | None = None
    rebalance_frequency: str = "weekly"
    mode: str = "precompute"
    skip_precompute: bool = False
    x_backtests: int = Field(default=1, ge=1, le=64)
    universe_filter: dict[str, Any] = Field(default_factory=dict)
    conditions: dict[str, Any] = Field(default_factory=dict)
    data_source: dict[str, Any] | None = None
    config: dict[str, Any] | None = None


class AgentDecisionResponse(BaseModel):
    id: str
    vt_symbol: str
    ts: datetime
    action: str
    size_pct: float
    confidence: float
    rating: str
    rationale: str | None = None
    token_cost_usd: float = 0.0
    provider: str | None = None
    deep_model: str | None = None
    quick_model: str | None = None
    crew_run_id: str | None = None


class DebateTurnResponse(BaseModel):
    id: str
    round: int
    side: str
    argument: str
    cites: list[str] = Field(default_factory=list)
    token_cost_usd: float = 0.0


class IngestRequest(BaseModel):
    symbols: list[str] | None = None
    start: str | None = None
    end: str | None = None
    interval: str = "1d"
    source: str | None = None


class UniverseSyncRequest(BaseModel):
    state: str = "active"
    limit: int | None = None
    include_otc: bool = False
    query: str | None = None


class DataSearchRequest(BaseModel):
    query: str
    k: int = 5


class DiscoverResponse(BaseModel):
    results: list[dict[str, Any]]


class IBKRHistoricalFetchRequest(BaseModel):
    vt_symbol: str = Field(..., description="e.g. AAPL.NASDAQ")
    start: str | None = Field(default=None, description="ISO datetime/date start")
    end: str | None = Field(default=None, description="ISO datetime/date end")
    end_date_time: str | None = Field(
        default=None,
        description="IBKR endDateTime override; used with duration_str",
    )
    duration_str: str | None = Field(
        default=None,
        description="IBKR duration string such as '10 D', '1 W', '3 M', '1 Y'",
    )
    bar_size: str = Field(default="1 day", description="IBKR bar size setting")
    what_to_show: str = Field(default="TRADES", description="TRADES | MIDPOINT | BID | ASK")
    use_rth: bool = Field(default=True, description="Regular trading hours only")
    exchange: str | None = Field(default=None, description="Routing exchange, default SMART")
    currency: str | None = Field(default=None, description="Currency, default USD")
    rows: int = Field(default=5000, ge=10, le=20000, description="Max rows returned to UI payload")

    @model_validator(mode="after")
    def _validate_time_args(self):
        if self.duration_str:
            return self
        if self.start or self.end:
            return self
        raise ValueError("Provide start/end or duration_str (with optional end_date_time).")


class IBKRHistoricalIngestRequest(IBKRHistoricalFetchRequest):
    overwrite: bool = Field(default=False, description="Overwrite existing symbol parquet files")


class BacktestSummary(BaseModel):
    id: str
    status: str
    start: datetime | None = None
    end: datetime | None = None
    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown: float | None = None
    total_return: float | None = None
    final_equity: float | None = None
    dataset_hash: str | None = None
    model_deployment_id: str | None = None
    created_at: datetime


class PortfolioSnapshot(BaseModel):
    cash: float
    equity: float
    positions: list[dict[str, Any]]


class KillSwitchRequest(BaseModel):
    reason: str = "manual"
    engage: bool = True


# ---------------------------------------------------------------------------
# Security (fundamentals / news / calendar / corporate / quote) responses.
# Every numeric field is optional because upstream providers (yfinance) are
# flaky — the UI renders ``—`` for missing values.
# ---------------------------------------------------------------------------


class FundamentalsResponse(BaseModel):
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    currency: str | None = None
    exchange: str | None = None
    website: str | None = None
    summary: str | None = None

    market_cap: float | None = None
    enterprise_value: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    peg_ratio: float | None = None

    dividend_yield: float | None = None
    dividend_rate: float | None = None
    payout_ratio: float | None = None
    shares_outstanding: float | None = None
    float_shares: float | None = None

    beta: float | None = None
    profit_margin: float | None = None
    operating_margin: float | None = None
    gross_margin: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None

    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    fifty_day_average: float | None = None
    two_hundred_day_average: float | None = None

    last_price: float | None = None
    previous_close: float | None = None
    day_high: float | None = None
    day_low: float | None = None

    cached: bool = False


class NewsItem(BaseModel):
    title: str
    publisher: str | None = None
    link: str | None = None
    published: str | None = None
    summary: str | None = None
    thumbnail: str | None = None
    related: list[str] = Field(default_factory=list)


class NewsResponse(BaseModel):
    ticker: str
    count: int
    items: list[NewsItem] = Field(default_factory=list)
    cached: bool = False


class EarningsEvent(BaseModel):
    date: str | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    surprise_pct: float | None = None


class CalendarResponse(BaseModel):
    ticker: str
    earnings_date: str | list[str] | None = None
    ex_dividend_date: str | None = None
    dividend_date: str | None = None
    earnings_high: float | None = None
    earnings_low: float | None = None
    earnings_average: float | None = None
    revenue_high: float | None = None
    revenue_low: float | None = None
    revenue_average: float | None = None
    earnings_history: list[EarningsEvent] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    cached: bool = False


class CorporateEvent(BaseModel):
    date: str
    value: float | None = None


class InstitutionalHolder(BaseModel):
    holder: str | None = None
    shares: float | None = None
    date_reported: str | None = None
    percent_out: float | None = None
    value: float | None = None


class CorporateActionsResponse(BaseModel):
    ticker: str
    dividends: list[CorporateEvent] = Field(default_factory=list)
    splits: list[CorporateEvent] = Field(default_factory=list)
    institutional_holders: list[InstitutionalHolder] = Field(default_factory=list)
    cached: bool = False


class QuoteSnapshot(BaseModel):
    ticker: str
    last: float | None = None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: float | None = None
    currency: str | None = None
    timestamp: str | None = None
    cached: bool = False
