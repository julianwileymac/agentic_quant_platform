"""SQLAlchemy ORM models — the Execution Ledger and agent-op audit trail."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    case,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


class Session(Base):
    __tablename__ = "sessions"
    id = Column(String(36), primary_key=True, default=_uuid)
    user = Column(String(120), nullable=False, default="local")
    title = Column(String(240), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)

    messages = relationship("ChatMessage", back_populates="session", cascade="all,delete")
    agent_runs = relationship("AgentRun", back_populates="session", cascade="all,delete")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), nullable=False)  # user | assistant | agent | tool
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    meta = Column(JSON, default=dict)

    session = relationship("Session", back_populates="messages")


class Strategy(Base):
    __tablename__ = "strategies"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(120), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    config_yaml = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(120), nullable=False, default="system")
    status = Column(String(32), nullable=False, default="draft")  # draft|backtesting|paper|live|retired
    meta = Column(JSON, default=dict)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=True)
    task_id = Column(String(120), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="pending")
    start = Column(DateTime, nullable=True)
    end = Column(DateTime, nullable=True)
    initial_cash = Column(Float, nullable=True)
    final_equity = Column(Float, nullable=True)
    sharpe = Column(Float, nullable=True)
    sortino = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    total_return = Column(Float, nullable=True)
    mlflow_run_id = Column(String(120), nullable=True)
    dataset_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    metrics = Column(JSON, default=dict)
    error = Column(Text, nullable=True)


class SignalEntry(Base):
    __tablename__ = "signals"
    id = Column(String(36), primary_key=True, default=_uuid)
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=True)
    backtest_id = Column(String(36), ForeignKey("backtest_runs.id"), nullable=True)
    vt_symbol = Column(String(40), nullable=False, index=True)
    direction = Column(String(10), nullable=False)
    strength = Column(Float, nullable=False)
    confidence = Column(Float, default=1.0)
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (Index("ix_signals_symbol_ts", "vt_symbol", "created_at"),)


class OrderRecord(Base):
    __tablename__ = "orders"
    id = Column(String(36), primary_key=True, default=_uuid)
    backtest_id = Column(String(36), ForeignKey("backtest_runs.id"), nullable=True)
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=True)
    vt_symbol = Column(String(40), nullable=False, index=True)
    side = Column(String(8), nullable=False)
    order_type = Column(String(16), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=True)
    status = Column(String(16), nullable=False, default="submitting")
    reference = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class Fill(Base):
    __tablename__ = "fills"
    id = Column(String(36), primary_key=True, default=_uuid)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=True)
    vt_symbol = Column(String(40), nullable=False, index=True)
    side = Column(String(8), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    slippage = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class LedgerEntry(Base):
    """The canonical Execution Ledger — every action, fill, and risk event."""

    __tablename__ = "ledger_entries"
    id = Column(String(36), primary_key=True, default=_uuid)
    backtest_id = Column(String(36), ForeignKey("backtest_runs.id"), nullable=True)
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=True)
    entry_type = Column(String(32), nullable=False, index=True)  # SIGNAL|ORDER|FILL|RISK|AGENT|META
    level = Column(String(16), nullable=False, default="info")   # debug|info|warn|error
    message = Column(Text, nullable=False)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (Index("ix_ledger_type_ts", "entry_type", "created_at"),)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=True)
    task_id = Column(String(120), nullable=True, index=True)
    crew = Column(String(120), nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    prompt = Column(Text, nullable=False)
    result = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    llm_model = Column(String(120), nullable=True)
    token_usage = Column(JSON, default=dict)

    session = relationship("Session", back_populates="agent_runs")


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    registry_name = Column(String(120), nullable=False, index=True)
    mlflow_version = Column(String(32), nullable=False)
    stage = Column(String(32), nullable=False, default="None")  # None|Staging|Production|Archived
    dataset_hash = Column(String(64), nullable=True)
    algo = Column(String(64), nullable=True)
    dataset_version_id = Column(String(36), ForeignKey("dataset_versions.id"), nullable=True, index=True)
    split_plan_id = Column(String(36), ForeignKey("split_plans.id"), nullable=True, index=True)
    pipeline_recipe_id = Column(String(36), ForeignKey("pipeline_recipes.id"), nullable=True, index=True)
    experiment_plan_id = Column(String(36), ForeignKey("experiment_plans.id"), nullable=True, index=True)
    metrics = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class RLEpisode(Base):
    """Snapshot of a single RL training episode for dashboards."""

    __tablename__ = "rl_episodes"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(120), nullable=False, index=True)
    episode = Column(Integer, nullable=False)
    mean_reward = Column(Float, nullable=False)
    portfolio_value = Column(Float, nullable=True)
    length = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class StrategyVersion(Base):
    """Immutable YAML snapshot of a strategy at a point in time."""

    __tablename__ = "strategy_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    strategy_id = Column(String(36), ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    config_yaml = Column(Text, nullable=False)
    author = Column(String(120), nullable=False, default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    dataset_hash = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_strategy_versions_strategy_version", "strategy_id", "version"),
    )


class StrategyTest(Base):
    """A test run of a strategy version against a specific window."""

    __tablename__ = "strategy_tests"
    id = Column(String(36), primary_key=True, default=_uuid)
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey("strategy_versions.id"), nullable=True)
    backtest_id = Column(String(36), ForeignKey("backtest_runs.id"), nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    start = Column(DateTime, nullable=True)
    end = Column(DateTime, nullable=True)
    sharpe = Column(Float, nullable=True)
    sortino = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    total_return = Column(Float, nullable=True)
    final_equity = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    engine = Column(String(64), nullable=True)


class OptimizationRun(Base):
    """Parent record for a parameter-sweep backtest job.

    The individual trials live in :class:`OptimizationTrial`. We keep metadata
    at the parent level (strategy, method, status, best metrics) so the
    Optimizer Lab UI can show a summary row per sweep without loading every
    trial.
    """

    __tablename__ = "optimization_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    task_id = Column(String(120), nullable=True, index=True)
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=True, index=True)
    run_name = Column(String(240), nullable=False, default="sweep")
    method = Column(String(32), nullable=False, default="grid")
    metric = Column(String(64), nullable=False, default="sharpe")
    status = Column(String(32), nullable=False, default="queued", index=True)
    n_trials = Column(Integer, nullable=False, default=0)
    n_completed = Column(Integer, nullable=False, default=0)
    best_trial_id = Column(String(36), nullable=True)
    best_metric_value = Column(Float, nullable=True)
    parameter_space = Column(JSON, default=dict)
    base_config = Column(JSON, default=dict)
    summary = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)


class OptimizationTrial(Base):
    """Single parameter draw + backtest outcome inside an ``OptimizationRun``."""

    __tablename__ = "optimization_trials"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), ForeignKey("optimization_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    backtest_id = Column(String(36), ForeignKey("backtest_runs.id"), nullable=True)
    trial_index = Column(Integer, nullable=False)
    parameters = Column(JSON, default=dict)
    status = Column(String(32), nullable=False, default="queued")
    metric_value = Column(Float, nullable=True)
    sharpe = Column(Float, nullable=True)
    sortino = Column(Float, nullable=True)
    total_return = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    final_equity = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class CrewRun(Base):
    """Lightweight index of agent-crew runs.

    ``AgentRun`` already stores the result payload but is keyed on
    ``session_id`` — it's hard to enumerate "all crews" or filter by name
    without that context. This table gives the Crew Trace UI a cheap
    surface to list + filter runs. Emitted alongside each crew kickoff by
    the Celery task in :mod:`aqp.tasks.agent_tasks`.
    """

    __tablename__ = "crew_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    task_id = Column(String(120), nullable=False, unique=True, index=True)
    crew_name = Column(String(120), nullable=False, default="research")
    # ``crew_type`` separates the existing research workflow from the new
    # TradingAgents-style trader workflow so UIs can filter. Values:
    # ``research`` (default) | ``trader``.
    crew_type = Column(String(32), nullable=False, default="research", index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    prompt = Column(Text, nullable=False)
    session_id = Column(String(36), nullable=True, index=True)
    agent_run_id = Column(String(36), ForeignKey("agent_runs.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    result = Column(JSON, default=dict)
    events = Column(JSON, default=list)
    error = Column(Text, nullable=True)
    cost_usd = Column(Float, nullable=False, default=0.0)


class PaperTradingRun(Base):
    """One row per paper / live trading session.

    Orders, fills, and ledger entries already live in their own tables and
    are correlated via ``reference="paper:<run_id>"`` on ``OrderRecord`` so
    the existing ``/portfolio/*`` endpoints work unchanged.
    """

    __tablename__ = "paper_trading_runs"
    id = Column(String(48), primary_key=True, default=_uuid)
    task_id = Column(String(120), nullable=True, index=True)
    run_name = Column(String(240), nullable=False, default="paper-adhoc")
    strategy_id = Column(String(120), nullable=True, index=True)
    brokerage = Column(String(40), nullable=False, default="sim")
    feed = Column(String(40), nullable=False, default="replay")
    status = Column(String(32), nullable=False, default="pending", index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_heartbeat_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    initial_cash = Column(Float, nullable=True)
    final_equity = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    bars_seen = Column(Integer, nullable=False, default=0)
    orders_submitted = Column(Integer, nullable=False, default=0)
    fills = Column(Integer, nullable=False, default=0)
    config = Column(JSON, default=dict)
    state = Column(JSON, default=dict)
    error = Column(Text, nullable=True)


class Instrument(Base):
    """Security master row keyed by the canonical ``vt_symbol``.

    As of the domain-model expansion, this is the **polymorphic parent** of
    the joined-table subclass tables in :mod:`aqp.persistence.models_instruments`
    (``instrument_equity``, ``instrument_option``, ``instrument_future``,
    ``instrument_fx_pair``, ``instrument_etf``, ``instrument_index``,
    ``instrument_bond``, ``instrument_crypto``, ``instrument_cfd``,
    ``instrument_commodity``, ``instrument_betting``, ``instrument_synthetic``,
    ``instrument_tokenized_asset``).

    ``instrument_class`` is the SQLAlchemy discriminator. Existing rows
    carry ``NULL`` in that column and resolve to the base ``Instrument``
    shape; new rows written by
    :func:`aqp.data.catalog._upsert_instruments` set the right subclass
    identity based on ``Symbol.asset_class`` + ``security_type``.
    """

    __tablename__ = "instruments"
    id = Column(String(36), primary_key=True, default=_uuid)
    vt_symbol = Column(String(64), nullable=False, unique=True, index=True)
    ticker = Column(String(64), nullable=False, index=True)
    exchange = Column(String(32), nullable=True)
    asset_class = Column(String(32), nullable=True)
    security_type = Column(String(32), nullable=True)
    instrument_class = Column(String(32), nullable=True, index=True)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    identifiers = Column(JSON, default=dict)
    sector = Column(String(120), nullable=True)
    industry = Column(String(120), nullable=True)
    region = Column(String(64), nullable=True)
    currency = Column(String(16), nullable=True)
    tick_size = Column(Float, nullable=True)
    multiplier = Column(Float, nullable=True)
    min_quantity = Column(Float, nullable=True)
    max_quantity = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=True)
    price_precision = Column(Integer, nullable=True)
    size_precision = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    tags = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Use a SQL CASE expression so rows with NULL ``instrument_class``
    # (legacy rows written before the domain-model expansion) still load
    # as the base :class:`Instrument` under the ``"_base"`` identity.
    __mapper_args__ = {
        "polymorphic_on": case(
            (instrument_class.is_(None), "_base"),
            else_=instrument_class,
        ),
        "polymorphic_identity": "_base",
    }


class DatasetCatalog(Base):
    """Logical dataset descriptor (provider/domain/schema family)."""

    __tablename__ = "dataset_catalogs"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(160), nullable=False, index=True)
    provider = Column(String(80), nullable=False, index=True)
    domain = Column(String(120), nullable=False, default="market.bars")
    frequency = Column(String(32), nullable=True)
    storage_uri = Column(String(512), nullable=True)
    schema_json = Column(JSON, default=dict)
    description = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    # Iceberg-first catalog columns (migration 0011).
    iceberg_identifier = Column(String(240), nullable=True, index=True)
    load_mode = Column(String(32), nullable=False, default="managed")
    source_uri = Column(String(1024), nullable=True)
    llm_annotations = Column(JSON, default=dict)
    column_docs = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_dataset_catalog_name_provider", "name", "provider"),
    )


class DatasetVersion(Base):
    """Materialized snapshot of a dataset at a point in time."""

    __tablename__ = "dataset_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    catalog_id = Column(
        String(36),
        ForeignKey("dataset_catalogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="active", index=True)
    as_of = Column(DateTime, nullable=True, index=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    symbol_count = Column(Integer, nullable=False, default=0)
    file_count = Column(Integer, nullable=False, default=0)
    dataset_hash = Column(String(64), nullable=True, index=True)
    materialization_uri = Column(String(512), nullable=True)
    columns = Column(JSON, default=list)
    schema_json = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    catalog = relationship("DatasetCatalog")
    experiment_plans = relationship("ExperimentPlan", back_populates="dataset_version")

    __table_args__ = (
        Index("ix_dataset_versions_catalog_version", "catalog_id", "version"),
    )


class SplitPlan(Base):
    """Deterministic split design and metadata."""

    __tablename__ = "split_plans"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(180), nullable=False, index=True)
    method = Column(String(40), nullable=False, default="fixed")
    description = Column(Text, nullable=True)
    dataset_version_id = Column(String(36), ForeignKey("dataset_versions.id"), nullable=True, index=True)
    dataset_hash = Column(String(64), nullable=True, index=True)
    config = Column(JSON, default=dict)
    segments = Column(JSON, default=dict)
    created_by = Column(String(120), nullable=False, default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    dataset_version = relationship("DatasetVersion")
    artifacts = relationship("SplitArtifact", back_populates="split_plan", cascade="all,delete")


class SplitArtifact(Base):
    """Materialized fold/segment boundaries and integer index sets."""

    __tablename__ = "split_artifacts"
    id = Column(String(36), primary_key=True, default=_uuid)
    split_plan_id = Column(
        String(36),
        ForeignKey("split_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fold_name = Column(String(64), nullable=False, default="default")
    segment = Column(String(32), nullable=False, default="train")
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    indices = Column(JSON, default=list)
    meta = Column(JSON, default=dict)

    split_plan = relationship("SplitPlan", back_populates="artifacts")

    __table_args__ = (
        Index("ix_split_artifacts_plan_fold_segment", "split_plan_id", "fold_name", "segment"),
    )


class PipelineRecipe(Base):
    """Configurable preprocessing recipe for learn/infer parity."""

    __tablename__ = "pipeline_recipes"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(180), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    description = Column(Text, nullable=True)
    shared_processors = Column(JSON, default=list)
    infer_processors = Column(JSON, default=list)
    learn_processors = Column(JSON, default=list)
    fit_window = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    meta = Column(JSON, default=dict)
    created_by = Column(String(120), nullable=False, default="system")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_pipeline_recipes_name_version", "name", "version"),
    )


class ExperimentPlan(Base):
    """Research plan tying data lineage, split and pipeline to model config."""

    __tablename__ = "experiment_plans"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(180), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    dataset_version_id = Column(String(36), ForeignKey("dataset_versions.id"), nullable=True, index=True)
    split_plan_id = Column(String(36), ForeignKey("split_plans.id"), nullable=True, index=True)
    pipeline_recipe_id = Column(String(36), ForeignKey("pipeline_recipes.id"), nullable=True, index=True)
    dataset_cfg = Column(JSON, default=dict)
    model_cfg = Column(JSON, default=dict)
    notes = Column(Text, nullable=True)
    tags = Column(JSON, default=list)
    created_by = Column(String(120), nullable=False, default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_run_id = Column(String(120), nullable=True)

    dataset_version = relationship("DatasetVersion", back_populates="experiment_plans")
    split_plan = relationship("SplitPlan")
    pipeline_recipe = relationship("PipelineRecipe")


class ModelDeployment(Base):
    """Deploy a trained model version as a reusable strategy alpha profile."""

    __tablename__ = "model_deployments"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(180), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="staging", index=True)
    model_version_id = Column(String(36), ForeignKey("model_versions.id"), nullable=False, index=True)
    experiment_plan_id = Column(String(36), ForeignKey("experiment_plans.id"), nullable=True, index=True)
    dataset_version_id = Column(String(36), ForeignKey("dataset_versions.id"), nullable=True, index=True)
    split_plan_id = Column(String(36), ForeignKey("split_plans.id"), nullable=True, index=True)
    pipeline_recipe_id = Column(String(36), ForeignKey("pipeline_recipes.id"), nullable=True, index=True)
    alpha_class = Column(String(64), nullable=False, default="DeployedModelAlpha")
    infer_segment = Column(String(32), nullable=False, default="infer")
    long_threshold = Column(Float, nullable=False, default=0.001)
    short_threshold = Column(Float, nullable=False, default=-0.001)
    allow_short = Column(Boolean, nullable=False, default=True)
    top_k = Column(Integer, nullable=True)
    deployment_config = Column(JSON, default=dict)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    model_version = relationship("ModelVersion")
    experiment_plan = relationship("ExperimentPlan")
    dataset_version = relationship("DatasetVersion")
    split_plan = relationship("SplitPlan")
    pipeline_recipe = relationship("PipelineRecipe")


# ---------------------------------------------------------------------------
# Agentic trading (TradingAgents-style LLM trader crew)
# ---------------------------------------------------------------------------


class AgentDecision(Base):
    """One structured LLM-trader decision for a ``(symbol, timestamp)``.

    Produced by :func:`aqp.agents.trading.propagate.propagate` and consumed
    by :class:`aqp.strategies.agentic.agentic_alpha.AgenticAlpha`. Stored
    so the Backtest Lab can render a Decision Timeline alongside the
    equity curve.
    """

    __tablename__ = "agent_decisions"
    id = Column(String(36), primary_key=True, default=_uuid)
    backtest_id = Column(String(36), ForeignKey("backtest_runs.id"), nullable=True, index=True)
    strategy_id = Column(String(36), ForeignKey("strategies.id"), nullable=True, index=True)
    crew_run_id = Column(String(36), ForeignKey("crew_runs.id"), nullable=True, index=True)
    vt_symbol = Column(String(40), nullable=False, index=True)
    ts = Column(DateTime, nullable=False, index=True)
    action = Column(String(8), nullable=False, default="HOLD")  # BUY | SELL | HOLD
    size_pct = Column(Float, nullable=False, default=0.0)
    confidence = Column(Float, nullable=False, default=0.5)
    rating = Column(String(16), nullable=False, default="hold")
    rationale = Column(Text, nullable=True)
    evidence = Column(JSON, default=list)
    provider = Column(String(32), nullable=True)
    deep_model = Column(String(120), nullable=True)
    quick_model = Column(String(120), nullable=True)
    token_cost_usd = Column(Float, nullable=False, default=0.0)
    context_hash = Column(String(64), nullable=True, index=True)
    payload = Column(JSON, default=dict)  # Full AgentDecision serialization
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_agent_decisions_symbol_ts", "vt_symbol", "ts"),
        Index("ix_agent_decisions_backtest_ts", "backtest_id", "ts"),
    )


class DebateTurn(Base):
    """A single Bull/Bear utterance captured during a trader crew run."""

    __tablename__ = "debate_turns"
    id = Column(String(36), primary_key=True, default=_uuid)
    crew_run_id = Column(
        String(36),
        ForeignKey("crew_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_id = Column(String(36), ForeignKey("agent_decisions.id"), nullable=True, index=True)
    round = Column(Integer, nullable=False, default=0)
    side = Column(String(8), nullable=False)  # bull | bear
    argument = Column(Text, nullable=False)
    cites = Column(JSON, default=list)
    token_cost_usd = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_debate_turns_crew_round", "crew_run_id", "round"),)


class AgentBacktest(Base):
    """Sidecar row per ``BacktestRun`` for runs powered by an LLM trader.

    The main ``BacktestRun`` row still owns equity/metrics; this table
    captures the LLM-specific metadata (provider, deep/quick model,
    debate rounds, total USD cost, decision cache location) so the
    Agentic tab in the Backtest Lab can render it without re-parsing
    the JSON ``metrics`` blob.
    """

    __tablename__ = "agent_backtests"
    id = Column(String(36), primary_key=True, default=_uuid)
    backtest_id = Column(
        String(36),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    mode = Column(String(32), nullable=False, default="precompute")  # precompute|audit|live
    provider = Column(String(32), nullable=True)
    deep_model = Column(String(120), nullable=True)
    quick_model = Column(String(120), nullable=True)
    max_debate_rounds = Column(Integer, nullable=False, default=1)
    n_decisions = Column(Integer, nullable=False, default=0)
    n_debate_turns = Column(Integer, nullable=False, default=0)
    total_token_cost_usd = Column(Float, nullable=False, default=0.0)
    decision_cache_uri = Column(String(512), nullable=True)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AgentJudgeReport(Base):
    """LLM/agent-as-judge critique over a backtest's decision trace.

    Written by the ``run_agentic_judge`` Celery task and read by the
    Backtest Detail Judge tab. One row per ``(backtest_id, judge_class)``
    pair so users can compare critiques from multiple judges side by
    side.
    """

    __tablename__ = "agent_judge_reports"
    id = Column(String(36), primary_key=True, default=_uuid)
    backtest_id = Column(
        String(36),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    judge_class = Column(String(64), nullable=False, default="LLMJudge")
    score = Column(Float, nullable=False, default=0.0)
    summary = Column(Text, nullable=True)
    findings = Column(JSON, default=list)
    cost_usd = Column(Float, nullable=False, default=0.0)
    provider = Column(String(64), nullable=True)
    model = Column(String(160), nullable=True)
    rubric = Column(String(64), nullable=True, default="default")
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_agent_judge_reports_backtest_judge", "backtest_id", "judge_class"),
    )


class AgentReplayRun(Base):
    """Counterfactual replay linking an original backtest to its child.

    Written when the user applies one or more :class:`Finding` edits via
    ``POST /agentic/replay/{backtest_id}``. The child backtest run still
    exists in :class:`BacktestRun`; this table just records the
    parent-child relationship + the diff of edits applied.
    """

    __tablename__ = "agent_replay_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    parent_backtest_id = Column(
        String(36),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    child_backtest_id = Column(
        String(36),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    judge_report_id = Column(
        String(36),
        ForeignKey("agent_judge_reports.id"),
        nullable=True,
        index=True,
    )
    edits = Column(JSON, default=list)
    created_by = Column(String(120), nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="queued")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)


class BacktestInterrupt(Base):
    """Pending HITL interrupt raised mid-backtest.

    Phase-2 scaffold for live pause/resume. The engine writes one row
    when an order matches a configured interrupt rule and blocks until
    the row's ``status`` flips from ``pending`` to ``resolved`` (or
    ``expired``). The UI fetches pending rows for the running backtest
    and posts a response back via
    ``POST /backtest/interrupts/{id}/respond``.
    """

    __tablename__ = "backtest_interrupts"
    id = Column(String(36), primary_key=True, default=_uuid)
    backtest_id = Column(
        String(36),
        ForeignKey("backtest_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_id = Column(String(64), nullable=True, index=True)
    ts = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    rule = Column(String(120), nullable=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    payload = Column(JSON, default=dict)
    response = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)


class FeatureSet(Base):
    """Named, versioned bundle of indicator / model-prediction specs.

    A ``FeatureSet`` is the canonical way to describe "the feature panel
    my alpha / ML model / RL env consumes". Specs are the same strings
    :class:`aqp.data.indicators_zoo.IndicatorZoo` parses (``"SMA:20"``,
    ``"MACD"``, ``"ModelPred:deployment_id=abc,column_name=xyz"``), so
    backtests, training, live trading, and RL share one source of truth.
    """

    __tablename__ = "feature_sets"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(160), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    kind = Column(String(32), nullable=False, default="indicator")
    # indicator | model_pred | composite
    specs = Column(JSON, default=list)  # list[str]
    default_lookback_days = Column(Integer, nullable=False, default=60)
    tags = Column(JSON, default=list)
    created_by = Column(String(120), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(24), nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FeatureSetVersion(Base):
    """Historical snapshot — one row per ``PUT /feature-sets/{id}`` bump."""

    __tablename__ = "feature_set_versions"
    id = Column(String(36), primary_key=True, default=_uuid)
    feature_set_id = Column(
        String(36),
        ForeignKey("feature_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False)
    specs = Column(JSON, default=list)
    notes = Column(Text, nullable=True)
    created_by = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_feature_set_versions_fs_version", "feature_set_id", "version"),
    )


class FeatureSetUsage(Base):
    """Lineage row written when a consumer (backtest / train / live / rl) uses a feature set."""

    __tablename__ = "feature_set_usages"
    id = Column(String(36), primary_key=True, default=_uuid)
    feature_set_id = Column(
        String(36),
        ForeignKey("feature_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=True)
    consumer_kind = Column(String(32), nullable=False, index=True)
    # backtest | train | live | rl | research
    consumer_id = Column(String(64), nullable=True, index=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class EquityReport(Base):
    """FinRobot-style section-agent equity research report.

    One row per generated report — the ``sections`` JSON carries the
    per-section agent output (tagline / company_overview / ... /
    news_summary). Surfaced by the Research tab in the webui.
    """

    __tablename__ = "equity_reports"
    id = Column(String(36), primary_key=True, default=_uuid)
    vt_symbol = Column(String(40), nullable=False, index=True)
    as_of = Column(DateTime, nullable=False, index=True)
    peers = Column(JSON, default=list)
    sections = Column(JSON, default=dict)
    usage = Column(JSON, default=dict)
    valuation = Column(JSON, default=dict)
    catalysts = Column(JSON, default=list)
    sensitivity = Column(JSON, default=dict)
    cost_usd = Column(Float, nullable=False, default=0.0)
    status = Column(String(24), nullable=False, default="completed")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_equity_reports_symbol_asof", "vt_symbol", "as_of"),
    )


# ---------------------------------------------------------------------------
# Data-plane expansion (Phase 1 of the data plane expansion plan).
#
# These tables provide a unified registry for remote data sources, a
# polymorphic identifier graph so every data source can tie back to the
# canonical :class:`Instrument`, and first-class masters for FRED series,
# SEC filings, and GDelt mentions that match registered instruments.
# ---------------------------------------------------------------------------


class DataSource(Base):
    """Registry of every data source AQP knows how to ingest from.

    Rows are seeded by the 0007 migration for the canonical providers
    (``fred``, ``sec_edgar``, ``gdelt``, ``yfinance``, ``polygon``,
    ``alpha_vantage``, ``ibkr``, ``local``, ``alpaca``, ``ccxt``) and
    can be enabled/disabled at runtime through the ``/sources`` API.

    ``credentials_ref`` stores the *name* of the env var / secret key
    that holds the credential (e.g. ``"AQP_FRED_API_KEY"``) — never the
    secret itself. The ``capabilities`` JSON documents which data
    domains the source covers and what frequencies / history windows
    are supported.
    """

    __tablename__ = "data_sources"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(64), nullable=False, unique=True, index=True)
    display_name = Column(String(160), nullable=False)
    kind = Column(String(32), nullable=False, default="rest_api")
    # rest_api | sdk | file_manifest | bigquery | local_file
    vendor = Column(String(120), nullable=True)
    auth_type = Column(String(32), nullable=False, default="none")
    # none | api_key | oauth2 | identity | service_account
    base_url = Column(String(512), nullable=True)
    protocol = Column(String(64), nullable=False, default="https/json")
    capabilities = Column(JSON, default=dict)
    rate_limits = Column(JSON, default=dict)
    credentials_ref = Column(String(120), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class IdentifierLink(Base):
    """Polymorphic, time-versioned identifier alias graph.

    Every row is one ``(entity, scheme, value)`` triple — an
    :class:`Instrument` with a CIK has one row, a FRED series with
    Federal Reserve release id has another. The design enables:

    * reverse lookup ``(scheme, value) -> entity`` via the composite
      index on ``(scheme, value)``;
    * forward fan-out "give me every identifier for this entity" via
      the ``(entity_kind, entity_id)`` index;
    * time-versioning so ticker rewrites (MapFile-style) stay truthful
      for historical queries.

    ``instrument_id`` is a denormalized FK kept up-to-date by the
    resolver — it's ``NULL`` for entities that don't correspond to a
    single instrument (a GDelt theme, a macro series) but set when the
    link ultimately resolves to one.
    """

    __tablename__ = "identifier_links"
    id = Column(String(36), primary_key=True, default=_uuid)
    entity_kind = Column(String(32), nullable=False, index=True)
    # instrument | fred_series | sec_filing | gdelt_theme | company
    entity_id = Column(String(64), nullable=False, index=True)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    scheme = Column(String(32), nullable=False, index=True)
    # ticker | vt_symbol | cik | cusip | isin | figi | sedol | lei |
    # gvkey | permid | openfigi | bbg_id | ric | gdelt_theme | fred_series_id
    value = Column(String(240), nullable=False, index=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    source_id = Column(String(36), ForeignKey("data_sources.id"), nullable=True, index=True)
    confidence = Column(Float, nullable=False, default=1.0)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_identifier_links_scheme_value", "scheme", "value"),
        Index(
            "ix_identifier_links_entity",
            "entity_kind",
            "entity_id",
        ),
        Index(
            "uq_identifier_links_unique",
            "entity_kind",
            "scheme",
            "value",
            "valid_from",
            unique=True,
        ),
    )


class DataLink(Base):
    """"Dataset version X contains data about entity Y" coverage row.

    Emitted whenever a :class:`DatasetVersion` is materialized so the
    UI can answer "what data do we have for this instrument?" without
    scanning every parquet file. One row per ``(dataset_version, entity)``
    pair; multiple rows per dataset when it covers a universe.
    """

    __tablename__ = "data_links"
    id = Column(String(36), primary_key=True, default=_uuid)
    dataset_version_id = Column(
        String(36),
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id = Column(String(36), ForeignKey("data_sources.id"), nullable=True, index=True)
    entity_kind = Column(String(32), nullable=False, index=True)
    entity_id = Column(String(64), nullable=False, index=True)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    coverage_start = Column(DateTime, nullable=True)
    coverage_end = Column(DateTime, nullable=True)
    row_count = Column(Integer, nullable=False, default=0)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ix_data_links_instrument_kind",
            "instrument_id",
            "entity_kind",
        ),
    )


class FredSeries(Base):
    """FRED economic-series master.

    Stores metadata for a Federal Reserve series (``DGS10``,
    ``UNRATE``, ``CPIAUCSL``, ...). Observations themselves live in
    the Parquet lake under ``{parquet_dir}/fred/{series_id}.parquet``
    and are tracked via :class:`DatasetCatalog` / :class:`DatasetVersion`.
    """

    __tablename__ = "fred_series"
    id = Column(String(36), primary_key=True, default=_uuid)
    series_id = Column(String(64), nullable=False, unique=True, index=True)
    title = Column(String(512), nullable=False, default="")
    units = Column(String(120), nullable=True)
    units_short = Column(String(60), nullable=True)
    frequency = Column(String(32), nullable=True)
    # Daily | Weekly | Monthly | Quarterly | Annual
    frequency_short = Column(String(8), nullable=True)
    seasonal_adj = Column(String(16), nullable=True)  # SA | NSA | SAAR
    seasonal_adj_short = Column(String(8), nullable=True)
    category_id = Column(Integer, nullable=True)
    release_id = Column(Integer, nullable=True)
    source_id = Column(String(36), ForeignKey("data_sources.id"), nullable=True, index=True)
    observation_start = Column(DateTime, nullable=True)
    observation_end = Column(DateTime, nullable=True)
    popularity = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    last_updated = Column(DateTime, nullable=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SecFiling(Base):
    """SEC EDGAR filing master.

    One row per filing (``10-K``, ``10-Q``, ``8-K``, ``4``, ``13F-HR``,
    ``DEF 14A``, ...). Parsed artifacts (financial statements, insider
    transactions, holdings) are materialized as Parquet under
    ``{parquet_dir}/sec/`` with domain ``filings.xbrl`` / ``filings.insider``
    / ``filings.ownership``.
    """

    __tablename__ = "sec_filings"
    id = Column(String(36), primary_key=True, default=_uuid)
    cik = Column(String(16), nullable=False, index=True)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    accession_no = Column(String(32), nullable=False, unique=True, index=True)
    form = Column(String(32), nullable=False, index=True)
    filed_at = Column(DateTime, nullable=False, index=True)
    period_of_report = Column(DateTime, nullable=True)
    primary_doc_url = Column(String(1024), nullable=True)
    primary_doc_type = Column(String(16), nullable=True)
    xbrl_available = Column(Boolean, nullable=False, default=False)
    items = Column(JSON, default=list)
    text_storage_uri = Column(String(1024), nullable=True)
    source_id = Column(String(36), ForeignKey("data_sources.id"), nullable=True, index=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_sec_filings_cik_form", "cik", "form"),
        Index("ix_sec_filings_cik_filed_at", "cik", "filed_at"),
    )


class GDeltMention(Base):
    """Lean row for GDelt GKG events that match a registered instrument.

    The full GDelt dataset (~2.5 TB/year) lives in the Parquet lake
    under ``{parquet_dir}/gdelt/year=YYYY/month=MM/day=DD/``. This
    table only indexes the subset of GKG records that mention a
    registered :class:`Instrument` via its organization names or
    identifiers — so day-to-day queries like "recent negative
    sentiment about AAPL" stay on a Postgres-friendly footprint.
    """

    __tablename__ = "gdelt_mentions"
    id = Column(String(36), primary_key=True, default=_uuid)
    gkg_record_id = Column(String(64), nullable=False, unique=True, index=True)
    date = Column(DateTime, nullable=False, index=True)
    source_common_name = Column(String(240), nullable=True)
    document_identifier = Column(String(2048), nullable=True)
    instrument_id = Column(String(36), ForeignKey("instruments.id"), nullable=True, index=True)
    themes = Column(JSON, default=list)
    tone = Column(JSON, default=dict)
    organizations_match = Column(JSON, default=list)
    source_id = Column(String(36), ForeignKey("data_sources.id"), nullable=True, index=True)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_gdelt_mentions_instrument_date", "instrument_id", "date"),
    )
