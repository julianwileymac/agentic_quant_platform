"""35-node :class:`NodeType` registry for the Data Lab.

Each :class:`NodeType` describes one of the 35 canonical operations
(plus user-authored ``snippet.python`` and a few math extras). The
record is the source of truth for:

- The palette tile in the React Flow editor (label / category / accent).
- The JSON-Schema-driven params form in the inspector (auto-generated
  from the bundled Pydantic params model).
- The executor dispatcher (alias → import path of an
  ``execute(spec: NodeSpec, ctx: NodeContext) -> NodeResult`` callable).
- The compiler's structural validator (typed inputs / outputs).

AGENTS rule discipline:

- Executors that need Iceberg writes go through
  :func:`aqp.data.iceberg_catalog.append_arrow` (rule 3).
- Executors that need LLM completions go through
  :func:`aqp.llm.providers.router.router_complete` (rule 2).
- Executors that need agent calls go through
  :class:`aqp.agents.runtime.AgentRuntime` (rule 12).
- Executors that need RL training go through
  :class:`aqp.rl.runtime.RLRuntime` (rule 16).
- Executors that need analysis flows go through
  :class:`aqp.analysis.runtime.AnalysisRuntime` (rule 23).

Phase 0 ships THREE real executors (``data.iceberg_scan``,
``xform.rank``, ``out.tearsheet``). The other 32 are registered as
placeholders that emit a structured ``not_implemented`` error so the
end-to-end frontend / compiler / WS contract can be exercised without
each executor blocking the foundation.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Literal

from aqp.lab.schema import NodeRuntime, Port, PortDType

logger = logging.getLogger(__name__)


CategoryName = Literal[
    "DataSource",
    "Transformation",
    "Feature",
    "Alpha",
    "Model",
    "Strategy",
    "Math",
    "Labeler",
    "Output",
    "Agent",
]


@dataclass(frozen=True)
class NodeType:
    """One entry in the 35-node taxonomy."""

    alias: str
    category: CategoryName
    label: str
    description: str
    inputs: tuple[Port, ...] = ()
    outputs: tuple[Port, ...] = ()
    runtime: NodeRuntime = field(default_factory=NodeRuntime)
    executor: str = "aqp.lab.executors._placeholder:execute"
    eda_executor: str | None = None
    sim_executor: str | None = None
    params_schema: dict[str, Any] = field(default_factory=dict)
    accent: str | None = None


# ---------------------------------------------------------------------------
# Convenience constructors (keep the table readable)
# ---------------------------------------------------------------------------


def _p(name: str, dtype: PortDType, *, optional: bool = False) -> Port:
    return Port(name=name, dtype=dtype, optional=optional)


def _placeholder_executor() -> str:
    return "aqp.lab.executors._placeholder:execute"


# ---------------------------------------------------------------------------
# The 35-node taxonomy (one tuple, single source of truth)
# ---------------------------------------------------------------------------

NODE_TYPES: tuple[NodeType, ...] = (
    # ------------------------- Data Sources (6)
    NodeType(
        alias="data.iceberg_scan",
        category="DataSource",
        label="Iceberg Scan",
        description=(
            "Read a slice of an Iceberg table via the sanctioned "
            "iceberg_catalog.read_arrow wrapper (AGENTS rule 3 read-side)."
        ),
        outputs=(_p("out", PortDType.FRAME),),
        executor="aqp.lab.executors.data_iceberg_scan:execute",
        accent="#1f6feb",
    ),
    NodeType(
        alias="data.hudi_scan",
        category="DataSource",
        label="Hudi Scan",
        description="Read a Hudi snapshot via the sanctioned HudiReader.",
        outputs=(_p("out", PortDType.FRAME),),
        executor="aqp.lab.executors.data_hudi_scan:execute",
        accent="#1f6feb",
    ),
    NodeType(
        alias="data.questdb_query",
        category="DataSource",
        label="QuestDB Query",
        description="Time-series PGWire query against QuestDB via asyncpg.",
        outputs=(_p("out", PortDType.BAR_SERIES),),
        executor="aqp.lab.executors.data_questdb_query:execute",
        accent="#1f6feb",
    ),
    NodeType(
        alias="data.duckdb_sql",
        category="DataSource",
        label="DuckDB SQL",
        description=(
            "Ad-hoc SQL via DuckDB over Iceberg / Parquet — no Postgres reads."
        ),
        outputs=(_p("out", PortDType.FRAME),),
        executor="aqp.lab.executors.data_duckdb_sql:execute",
        accent="#1f6feb",
    ),
    NodeType(
        alias="data.redpanda_subscribe",
        category="DataSource",
        label="Redpanda Subscribe",
        description="Live Kafka subscribe — Simulation mode only.",
        outputs=(_p("out", PortDType.TICK_STREAM),),
        runtime=NodeRuntime(target="dagster"),
        executor="aqp.lab.executors.data_redpanda_subscribe:execute",
        accent="#1f6feb",
    ),
    NodeType(
        alias="data.synthetic",
        category="DataSource",
        label="Synthetic Series",
        description="Generate synthetic OHLCV from a math.* upstream.",
        outputs=(_p("out", PortDType.BAR_SERIES),),
        executor="aqp.lab.executors.data_synthetic:execute",
        accent="#1f6feb",
    ),
    # ------------------------- Transformations (5)
    NodeType(
        alias="xform.resample",
        category="Transformation",
        label="Resample",
        description="Time-bar resample with gap-aware handling.",
        inputs=(_p("in", PortDType.BAR_SERIES),),
        outputs=(_p("out", PortDType.BAR_SERIES),),
        executor="aqp.lab.executors.xform_resample:execute",
        accent="#7c3aed",
    ),
    NodeType(
        alias="xform.join_asof",
        category="Transformation",
        label="Join (asof)",
        description="ASOF JOIN for trades ↔ book correlation.",
        inputs=(
            _p("left", PortDType.FRAME),
            _p("right", PortDType.FRAME),
        ),
        outputs=(_p("out", PortDType.FRAME),),
        executor="aqp.lab.executors.xform_join_asof:execute",
        accent="#7c3aed",
    ),
    NodeType(
        alias="xform.winsorize",
        category="Transformation",
        label="Winsorize",
        description="Quantile clipping per cross-section.",
        inputs=(_p("in", PortDType.PANEL),),
        outputs=(_p("out", PortDType.PANEL),),
        executor="aqp.lab.executors.xform_winsorize:execute",
        accent="#7c3aed",
    ),
    NodeType(
        alias="xform.neutralize",
        category="Transformation",
        label="Neutralize",
        description=(
            "Sector / country / size / market neutralization — wraps the "
            "vector_neut / group_neutralize / regression_neut helpers in "
            "aqp.data.expressions_dsl (BRAIN semantics)."
        ),
        inputs=(_p("alpha", PortDType.SIGNAL),),
        outputs=(_p("out", PortDType.SIGNAL),),
        executor="aqp.lab.executors.xform_neutralize:execute",
        accent="#7c3aed",
    ),
    NodeType(
        alias="xform.rank",
        category="Transformation",
        label="Rank",
        description="Cross-sectional rank / z-score / bucket.",
        inputs=(_p("in", PortDType.PANEL),),
        outputs=(_p("out", PortDType.PANEL),),
        executor="aqp.lab.executors.xform_rank:execute",
        accent="#7c3aed",
    ),
    # ------------------------- Features (4)
    NodeType(
        alias="feature.technical",
        category="Feature",
        label="Technical (TA-Lib / VBT)",
        description="MA / RSI / MACD / ADX / Bollinger / SuperTrend / Donchian.",
        inputs=(_p("in", PortDType.BAR_SERIES),),
        outputs=(_p("out", PortDType.PANEL),),
        executor="aqp.lab.executors.feature_technical:execute",
        accent="#0ea5e9",
    ),
    NodeType(
        alias="feature.microstructure",
        category="Feature",
        label="Microstructure",
        description=(
            "Kyle's λ, Amihud, VPIN, Roll spread, OFI — wraps "
            "aqp.data.microstructure functions."
        ),
        inputs=(_p("in", PortDType.TICK_STREAM),),
        outputs=(_p("out", PortDType.PANEL),),
        executor="aqp.lab.executors.feature_microstructure:execute",
        accent="#0ea5e9",
    ),
    NodeType(
        alias="feature.fracdiff",
        category="Feature",
        label="Fractional Diff",
        description="Fixed-width fractional differentiation (López de Prado FFD).",
        inputs=(_p("in", PortDType.BAR_SERIES),),
        outputs=(_p("out", PortDType.BAR_SERIES),),
        executor="aqp.lab.executors.feature_fracdiff:execute",
        accent="#0ea5e9",
    ),
    NodeType(
        alias="feature.embedding",
        category="Feature",
        label="Embedding",
        description="sentence-transformers or time-series embedding → pgvector.",
        inputs=(_p("in", PortDType.FRAME),),
        outputs=(_p("out", PortDType.MODEL_ARTIFACT),),
        executor="aqp.lab.executors.feature_embedding:execute",
        accent="#0ea5e9",
    ),
    # ------------------------- Alphas (3)
    NodeType(
        alias="alpha.formulaic",
        category="Alpha",
        label="Formulaic Alpha",
        description=(
            "WorldQuant BRAIN-style expression DSL — wraps "
            "aqp.data.expressions_dsl.compile_to_factor_node "
            "with the AST sandbox (AGENTS rule 39)."
        ),
        inputs=(_p("bars", PortDType.BAR_SERIES),),
        outputs=(_p("out", PortDType.SIGNAL),),
        executor="aqp.lab.executors.alpha_formulaic:execute",
        accent="#f59e0b",
    ),
    NodeType(
        alias="alpha.ml",
        category="Alpha",
        label="ML Alpha",
        description="MLflow-tracked model emitting cross-sectional scores.",
        inputs=(
            _p("features", PortDType.PANEL),
            _p("model", PortDType.MODEL_ARTIFACT, optional=True),
        ),
        outputs=(_p("out", PortDType.SIGNAL),),
        executor="aqp.lab.executors.alpha_ml:execute",
        accent="#f59e0b",
    ),
    NodeType(
        alias="alpha.combine",
        category="Alpha",
        label="Alpha Combine",
        description="Linear / rank / factor-mimicking combiner.",
        inputs=(_p("alphas", PortDType.SIGNAL),),
        outputs=(_p("out", PortDType.SIGNAL),),
        executor="aqp.lab.executors.alpha_combine:execute",
        accent="#f59e0b",
    ),
    # ------------------------- Models (4)
    NodeType(
        alias="model.sklearn",
        category="Model",
        label="sklearn Model",
        description="sklearn estimator with optional purged_kfold / CPCV.",
        inputs=(
            _p("X", PortDType.PANEL),
            _p("y", PortDType.SIGNAL),
        ),
        outputs=(_p("out", PortDType.MODEL_ARTIFACT),),
        executor="aqp.lab.executors.model_sklearn:execute",
        accent="#dc2626",
    ),
    NodeType(
        alias="model.gbm",
        category="Model",
        label="GBM (XGBoost / LightGBM / CatBoost)",
        description="Gradient-boosted decision trees with MLflow autolog.",
        inputs=(
            _p("X", PortDType.PANEL),
            _p("y", PortDType.SIGNAL),
        ),
        outputs=(_p("out", PortDType.MODEL_ARTIFACT),),
        executor="aqp.lab.executors.model_gbm:execute",
        accent="#dc2626",
    ),
    NodeType(
        alias="model.torch",
        category="Model",
        label="PyTorch Module",
        description="PyTorch model from snippet path or registered architecture.",
        inputs=(
            _p("X", PortDType.PANEL),
            _p("y", PortDType.SIGNAL),
        ),
        outputs=(_p("out", PortDType.MODEL_ARTIFACT),),
        executor="aqp.lab.executors.model_torch:execute",
        accent="#dc2626",
    ),
    NodeType(
        alias="model.rl",
        category="Model",
        label="RL Trainer",
        description=(
            "Stable-Baselines3 / ElegantRL trainer — dispatches through "
            "RLRuntime (AGENTS rule 16)."
        ),
        inputs=(_p("env", PortDType.RL_ENV),),
        outputs=(_p("out", PortDType.RL_POLICY),),
        executor="aqp.lab.executors.model_rl:execute",
        accent="#dc2626",
    ),
    # ------------------------- Strategies (3)
    NodeType(
        alias="strategy.vbt_portfolio",
        category="Strategy",
        label="vectorbt-pro Portfolio",
        description=(
            "Portfolio.from_signals / from_orders / from_holding — wraps "
            "aqp.backtest.vbtpro.engine.VectorbtProEngine."
        ),
        inputs=(_p("signal", PortDType.SIGNAL),),
        outputs=(_p("out", PortDType.PORTFOLIO),),
        executor="aqp.lab.executors.strategy_vbt_portfolio:execute",
        accent="#10b981",
    ),
    NodeType(
        alias="strategy.lean_framework",
        category="Strategy",
        label="LEAN 5-Slot Framework",
        description="Universe → Alpha → PortfolioConstruction → Risk → Execution.",
        inputs=(_p("signal", PortDType.SIGNAL),),
        outputs=(_p("out", PortDType.PORTFOLIO),),
        executor="aqp.lab.executors.strategy_lean_framework:execute",
        accent="#10b981",
    ),
    NodeType(
        alias="strategy.hftbt_market_maker",
        category="Strategy",
        label="hftbacktest Market Maker",
        description=(
            "Numba @njit market-making strategy compatible with "
            "aqp.backtest.hft.LobBacktestEngine."
        ),
        inputs=(_p("lob", PortDType.ORDERBOOK_L2),),
        outputs=(_p("out", PortDType.PORTFOLIO),),
        runtime=NodeRuntime(target="dagster"),
        executor="aqp.lab.executors.strategy_hftbt_market_maker:execute",
        accent="#10b981",
    ),
    # ------------------------- Math / Stochastic (4)
    NodeType(
        alias="math.gbm",
        category="Math",
        label="GBM (Geometric Brownian Motion)",
        description="JAX-vmap'd GBM path simulator.",
        outputs=(_p("out", PortDType.BAR_SERIES),),
        executor="aqp.lab.executors.math_gbm:execute",
        accent="#8b5cf6",
    ),
    NodeType(
        alias="math.heston",
        category="Math",
        label="Heston SV",
        description="Heston stochastic-volatility paths.",
        outputs=(_p("out", PortDType.BAR_SERIES),),
        executor="aqp.lab.executors.math_heston:execute",
        accent="#8b5cf6",
    ),
    NodeType(
        alias="math.ou_jump",
        category="Math",
        label="OU + Jumps",
        description="Ornstein-Uhlenbeck mean reversion + Poisson jumps.",
        outputs=(_p("out", PortDType.BAR_SERIES),),
        executor="aqp.lab.executors.math_ou_jump:execute",
        accent="#8b5cf6",
    ),
    NodeType(
        alias="math.regime_hmm",
        category="Math",
        label="Regime HMM",
        description="Hidden Markov regime model; emits state-label signal.",
        inputs=(_p("in", PortDType.BAR_SERIES),),
        outputs=(_p("out", PortDType.SIGNAL),),
        executor="aqp.lab.executors.math_regime_hmm:execute",
        accent="#8b5cf6",
    ),
    # ------------------------- Labelers (3)
    NodeType(
        alias="label.triple_barrier",
        category="Labeler",
        label="Triple-Barrier (López de Prado)",
        description=(
            "mlfinlab triple-barrier — wraps "
            "aqp.ml.labeling.triple_barrier."
        ),
        inputs=(_p("bars", PortDType.BAR_SERIES),),
        outputs=(_p("out", PortDType.ANNOTATION_SET),),
        executor="aqp.lab.executors.label_triple_barrier:execute",
        accent="#ec4899",
    ),
    NodeType(
        alias="label.meta",
        category="Labeler",
        label="Meta-Label",
        description="Meta-labeling: 'take this bet?' classifier target.",
        inputs=(
            _p("primary", PortDType.SIGNAL),
            _p("labels", PortDType.ANNOTATION_SET),
        ),
        outputs=(_p("out", PortDType.ANNOTATION_SET),),
        executor="aqp.lab.executors.label_meta:execute",
        accent="#ec4899",
    ),
    NodeType(
        alias="label.trend_scan",
        category="Labeler",
        label="Trend Scan",
        description="Trend-scanning labels (sign + magnitude of trend).",
        inputs=(_p("bars", PortDType.BAR_SERIES),),
        outputs=(_p("out", PortDType.ANNOTATION_SET),),
        executor="aqp.lab.executors.label_trend_scan:execute",
        accent="#ec4899",
    ),
    # ------------------------- Outputs (2)
    NodeType(
        alias="out.tearsheet",
        category="Output",
        label="Tearsheet",
        description=(
            "QuantStats + alphalens-style IC / IR / quantile / turnover / "
            "cumulative-returns tearsheet — wraps "
            "aqp.tasks.analytics_tasks.render_portfolio_tearsheet."
        ),
        inputs=(_p("portfolio", PortDType.PORTFOLIO),),
        outputs=(_p("out", PortDType.JSON),),
        executor="aqp.lab.executors.output_tearsheet:execute",
        accent="#14b8a6",
    ),
    NodeType(
        alias="out.publish_mlflow",
        category="Output",
        label="Publish to MLflow",
        description="Register portfolio / model as MLflow artifact + bind to control plane.",
        inputs=(_p("portfolio", PortDType.PORTFOLIO),),
        outputs=(_p("out", PortDType.JSON),),
        executor="aqp.lab.executors.out_publish_mlflow:execute",
        accent="#14b8a6",
    ),
    # ------------------------- Agents (1)
    NodeType(
        alias="agent.crewai",
        category="Agent",
        label="CrewAI Agent",
        description=(
            "Spec-driven CrewAI / LangGraph agent — dispatches through "
            "AgentRuntime (AGENTS rule 12); all reads via DataMCP."
        ),
        inputs=(_p("context", PortDType.JSON, optional=True),),
        outputs=(_p("out", PortDType.AGENT_HANDLE),),
        executor="aqp.lab.executors.agent_crewai:execute",
        accent="#f97316",
    ),
    # ------------------------- Snippets (user-authored Python / SQL)
    # The snippet.* aliases are extension points for the EDA "Promote
    # to Testing" workflow + the user-authored node library. The
    # executor runs the snippet through the Tier-1 (Pyodide) /
    # Tier-2 (gVisor-Docker) sandbox per AGENTS rule 39 + plan §4.
    NodeType(
        alias="snippet.python",
        category="Transformation",
        label="Python Snippet",
        description=(
            "User-authored Python transform — sourced from a "
            "`lab_snippets` row + AST-validated. Phase 1 runs through "
            "the in-process EdaKernel; Phase 4 swaps to the gVisor "
            "Tier-2 sandbox."
        ),
        inputs=(_p("in", PortDType.FRAME, optional=True),),
        outputs=(_p("out", PortDType.FRAME),),
        executor="aqp.lab.executors.snippet_python:execute",
        accent="#7c3aed",
    ),
    NodeType(
        alias="snippet.sql",
        category="Transformation",
        label="SQL Snippet",
        description=(
            "User-authored SQL snippet — runs via DuckDB over upstream "
            "Arrow tables. No AST guard (SQL is sandboxed by the "
            "DuckDB policy check); credentials never inlined."
        ),
        inputs=(_p("in", PortDType.FRAME, optional=True),),
        outputs=(_p("out", PortDType.FRAME),),
        executor="aqp.lab.executors.snippet_sql:execute",
        accent="#7c3aed",
    ),
)


# ---------------------------------------------------------------------------
# Registry surface
# ---------------------------------------------------------------------------

_BY_ALIAS: dict[str, NodeType] = {nt.alias: nt for nt in NODE_TYPES}


def all_node_types() -> tuple[NodeType, ...]:
    """Return the immutable 35-node tuple."""
    return NODE_TYPES


def get_node_type(alias: str) -> NodeType:
    """Resolve a NodeType by alias; raise on unknown."""
    if alias not in _BY_ALIAS:
        raise KeyError(f"Unknown Data Lab node alias: {alias!r}")
    return _BY_ALIAS[alias]


def known_aliases() -> tuple[str, ...]:
    return tuple(sorted(_BY_ALIAS.keys()))


def categories_for_palette() -> dict[CategoryName, list[NodeType]]:
    """Group node types by UI category for the React Flow palette."""
    grouped: dict[CategoryName, list[NodeType]] = {}
    for nt in NODE_TYPES:
        grouped.setdefault(nt.category, []).append(nt)
    return grouped


def resolve_executor(alias: str, *, target: str = "celery") -> Callable[..., Any]:
    """Load the configured executor callable for a node alias.

    ``target`` selects the eda / sim variant when present; defaults to
    the primary ``executor`` field. Returns a callable with the
    contract ``(node_spec, ctx) -> NodeResult``.
    """
    nt = get_node_type(alias)
    if target == "eda" and nt.eda_executor:
        path = nt.eda_executor
    elif target == "simulation" and nt.sim_executor:
        path = nt.sim_executor
    else:
        path = nt.executor
    module_path, _, fn_name = path.partition(":")
    if not fn_name:
        raise ValueError(
            f"NodeType {alias!r} executor path missing ':function' suffix"
        )
    module = importlib.import_module(module_path)
    return getattr(module, fn_name)


__all__ = [
    "CategoryName",
    "NODE_TYPES",
    "NodeType",
    "all_node_types",
    "categories_for_palette",
    "get_node_type",
    "known_aliases",
    "resolve_executor",
]
