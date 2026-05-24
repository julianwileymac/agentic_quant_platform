"""Pydantic ``params`` models per :class:`NodeType`.

The Data Lab Testing-mode inspector renders the right-rail params
form by reading each NodeType's ``params_schema`` JSON Schema. The
schema is auto-generated from the Pydantic models defined here via
:meth:`pydantic.BaseModel.model_json_schema`. The catalog endpoint
(``GET /lab/catalog/node-types``) inlines the schema so the frontend
can lazy-render the form without a second round-trip.

Coverage is best-effort — every node type that ships with a real
executor SHOULD have a typed params model so the inspector renders a
typed form. Node types without a model fall through to a JSON-text
editor, which is still functional.

Adding a new params model:

1. Define a Pydantic ``BaseModel`` subclass with descriptive
   ``Field(..., description=..., title=...)`` annotations.
2. Register it in :data:`PARAMS_MODELS` keyed by the NodeType alias.
3. The next ``GET /lab/catalog/node-types`` call returns the
   updated JSON Schema.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------------------


class IcebergScanParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "DataSource"})

    namespace: str = Field(..., title="Iceberg namespace", description="e.g. aqp_silver_equities_bars")
    table: str = Field(..., title="Table name")
    columns: list[str] | None = Field(default=None, title="Columns")
    limit: int | None = Field(default=None, ge=1, title="Row limit")
    snapshot_id: int | None = Field(default=None, title="Pinned snapshot id")
    predicates: list[str] | None = Field(default=None, title="Row filter predicates")


class HudiScanParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "DataSource"})

    namespace: str = Field(..., title="Hudi namespace (will be wrapped to aqp_hudi_*)")
    table: str = Field(..., title="Table name")
    record_key_field: str = Field(default="id", title="Record key field")
    precombine_field: str = Field(default="ts", title="Precombine field")
    partition_path_field: str | None = Field(default=None, title="Partition path field")
    table_type: Literal["MERGE_ON_READ", "COPY_ON_WRITE"] = Field(default="MERGE_ON_READ")
    snapshot_query: str | None = Field(default=None, title="Snapshot SQL query")
    limit: int | None = Field(default=None, ge=1)


class QuestDBQueryParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "DataSource"})

    sql: str = Field(..., title="QuestDB SQL", description="Read-only SELECT against an allow-listed table.")
    table: str | None = Field(default=None, title="Primary table (for partition fingerprint)")


class DuckDbSqlParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "DataSource"})

    sql: str = Field(..., title="DuckDB SQL")


class RedpandaSubscribeParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "DataSource"})

    topic: str = Field(..., title="Topic name")
    cluster: Literal["strimzi", "redpanda"] | None = Field(default=None, title="Override cluster")
    group_id: str | None = Field(default=None, title="Consumer group id")
    max_messages: int = Field(default=200, ge=1, le=10_000)
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=120.0)
    start_from: Literal["earliest", "latest", "timestamp"] = Field(default="latest")
    start_timestamp_ms: int | None = Field(default=None, title="Start timestamp (ms epoch)")


class SyntheticParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "DataSource"})

    path_index: int = Field(default=0, ge=0, title="Path index")
    output_columns: Literal["close", "ohlcv"] = Field(default="close")
    volume: float = Field(default=1.0)
    jitter_pct: float = Field(default=0.001, ge=0.0, le=0.1)


# ---------------------------------------------------------------------------
# Transformations
# ---------------------------------------------------------------------------


class ResampleParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Transformation"})

    rule: str = Field(..., title="Resample rule", description='e.g. "1min", "5min", "1D".')
    timestamp_column: str = Field(default="datetime")
    aggregations: dict[str, str] | None = Field(
        default=None,
        title="Per-column aggregation",
        description='e.g. {"close": "last", "volume": "sum"}',
    )


class WinsorizeParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Transformation"})

    lower_q: float = Field(default=0.01, ge=0.0, le=0.49)
    upper_q: float = Field(default=0.99, ge=0.51, le=1.0)
    columns: list[str] | None = Field(default=None)


class NeutralizeParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Transformation"})

    method: Literal["group", "vector", "regression"] = Field(default="group")
    alpha_column: str = Field(default="alpha")
    group_column: str | None = Field(default=None)
    basis_column: str | None = Field(default=None)
    basis_columns: list[str] | None = Field(default=None)


class RankParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Transformation"})

    method: Literal["pct", "z", "bucket"] = Field(default="pct")
    buckets: int = Field(default=5, ge=2, le=100)
    columns: list[str] | None = Field(default=None)


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


class TechnicalParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Feature"})

    indicator: str = Field(..., title="Indicator", description="e.g. rsi, macd, atr")
    window: int = Field(default=14, ge=2, le=2_000)
    column: str = Field(default="close")
    alias: str | None = Field(default=None)


class MicrostructureParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Feature"})

    measure: Literal["kyle_lambda", "amihud", "vpin", "roll", "ofi"] = Field(...)
    alias: str | None = Field(default=None)
    bucket_size: int | None = Field(default=None, ge=2)
    window: int | None = Field(default=None, ge=2)


class FracdiffParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Feature"})

    d: float = Field(..., ge=0.0, le=1.0, title="Differencing exponent")
    threshold: float = Field(default=1e-4, ge=1e-8, le=1e-1)
    column: str = Field(default="close")
    alias: str | None = Field(default=None)


class EmbeddingParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Feature"})

    text_column: str = Field(default="text")
    id_column: str | None = Field(default=None)
    model: str | None = Field(default=None)
    max_rows: int = Field(default=5000, ge=1, le=200_000)


# ---------------------------------------------------------------------------
# Alphas
# ---------------------------------------------------------------------------


class FormulaicAlphaParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Alpha"})

    formula: str = Field(..., title="Symbolic formula")
    alias: str | None = Field(default=None)
    signal_clip: float | None = Field(default=None, ge=0.0)


class AlphaMlParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Alpha"})

    model_uri: str = Field(..., title="MLflow URI", description="e.g. models:/long_short_mom/Production")
    feature_columns: list[str] | None = Field(default=None)
    signal_clip: float | None = Field(default=None, ge=0.0)
    output_column: str = Field(default="signal")


class AlphaCombineParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Alpha"})

    method: Literal["linear", "rank", "equal"] = Field(default="linear")
    weights: dict[str, float] | None = Field(default=None)
    alpha_columns: list[str] | None = Field(default=None)
    alias: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SklearnModelParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Model"})

    estimator: Literal["linear", "ridge", "logistic", "rf_regressor", "rf_classifier"] = Field(...)
    target_column: str = Field(..., title="Target column")
    feature_columns: list[str] | None = Field(default=None)
    test_size: float = Field(default=0.25, ge=0.05, le=0.5)
    n_estimators: int | None = Field(default=None, ge=10, le=2000)
    random_state: int = Field(default=42)


class GbmModelParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Model"})

    framework: Literal["xgboost", "lightgbm", "catboost"] = Field(...)
    task: Literal["regression", "classification"] = Field(default="regression")
    target_column: str = Field(...)
    feature_columns: list[str] | None = Field(default=None)
    test_size: float = Field(default=0.25, ge=0.05, le=0.5)
    random_state: int = Field(default=42)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)


class TorchModelParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Model"})

    target_column: str = Field(...)
    task: Literal["regression", "classification"] = Field(default="regression")
    hidden_dims: list[int] = Field(default_factory=lambda: [64, 32])
    epochs: int = Field(default=25, ge=1, le=2_000)
    batch_size: int = Field(default=256, ge=1)
    lr: float = Field(default=1e-3, gt=0.0, le=1.0)
    test_size: float = Field(default=0.25, ge=0.05, le=0.5)
    random_state: int = Field(default=42)
    snippet_id: str | None = Field(default=None, title="Custom architecture snippet id (Phase 4)")


class RlModelParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Model"})

    action: Literal["train", "evaluate", "paper", "replay", "walk_forward"] = Field(default="train")
    spec_name: str | None = Field(default=None, title="Persisted RLExperimentSpec name")
    spec: dict[str, Any] | None = Field(default=None, title="Inline spec")
    run_name: str | None = Field(default=None)
    checkpoint: str | None = Field(default=None)
    overrides: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class VbtPortfolioParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Strategy"})

    mode: Literal["signals", "orders", "holding", "random"] = Field(default="signals")
    init_cash: float = Field(default=100_000.0, gt=0.0)
    fees: float = Field(default=0.001, ge=0.0, le=0.1)
    entries_column: str | None = Field(default=None)
    exits_column: str | None = Field(default=None)
    size_column: str | None = Field(default=None)


class LeanFrameworkParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Strategy"})

    lean_source: str | None = Field(default=None, title="QCAlgorithm source code")
    template_resource_id: str | None = Field(default=None, title="Strategy template id")
    class_name: str | None = Field(default=None)
    translate: bool = Field(default=True)
    name: str | None = Field(default=None, title="Clone target name")


class HftbtMarketMakerParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Strategy"})

    dataset_preset: str = Field(...)
    half_spread_bps: float = Field(default=5.0, ge=0.1, le=500.0)
    inventory_target: float = Field(default=0.0)
    inventory_gamma: float = Field(default=0.1, ge=0.0)
    max_events: int = Field(default=100_000, ge=1, le=10_000_000)
    latency_profile: Literal["low", "med", "high"] = Field(default="med")
    queue_model: Literal["pro_rata", "fifo"] = Field(default="pro_rata")


# ---------------------------------------------------------------------------
# Math
# ---------------------------------------------------------------------------


class GbmParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Math"})

    S0: float = Field(default=100.0)
    mu: float = Field(default=0.05)
    sigma: float = Field(default=0.2, gt=0.0)
    T: float = Field(default=1.0, gt=0.0)
    n_steps: int = Field(default=252, ge=1)
    n_paths: int = Field(default=1000, ge=1, le=100_000)
    seed: int = Field(default=42)


class HestonParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Math"})

    S0: float = Field(default=100.0)
    v0: float = Field(default=0.04, ge=0.0)
    kappa: float = Field(default=2.0, ge=0.0)
    theta: float = Field(default=0.04, ge=0.0)
    xi: float = Field(default=0.3, ge=0.0)
    rho: float = Field(default=-0.7, ge=-1.0, le=1.0)
    r: float = Field(default=0.0)
    T: float = Field(default=1.0, gt=0.0)
    n_steps: int = Field(default=252, ge=1)
    n_paths: int = Field(default=500, ge=1, le=100_000)
    seed: int = Field(default=42)


class OuJumpParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Math"})

    X0: float = Field(default=0.0)
    mu: float = Field(default=0.0)
    theta_speed: float = Field(default=1.0, ge=0.0)
    sigma: float = Field(default=0.2, ge=0.0)
    jump_intensity: float = Field(default=1.0, ge=0.0)
    jump_mean: float = Field(default=0.0)
    jump_std: float = Field(default=0.05, ge=0.0)
    T: float = Field(default=1.0, gt=0.0)
    n_steps: int = Field(default=252, ge=1)
    n_paths: int = Field(default=500, ge=1, le=100_000)
    seed: int = Field(default=42)


class RegimeHmmParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Math"})

    n_states: int = Field(default=3, ge=2, le=10)
    feature_column: str = Field(default="close")
    returns_lookback: int = Field(default=1, ge=1, le=50)
    backend: Literal["auto", "hmmlearn", "heuristic"] = Field(default="auto")


# ---------------------------------------------------------------------------
# Labelers
# ---------------------------------------------------------------------------


class TripleBarrierParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Labeler"})

    pt_sl: Annotated[list[float], Field(min_length=2, max_length=2)] = Field(default=[1.0, 1.0])
    vertical_barrier_days: int = Field(default=5, ge=1, le=365)
    min_return: float = Field(default=0.0, ge=0.0)
    price_column: str = Field(default="close")
    vol_column: str | None = Field(default=None)


class MetaLabelParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Labeler"})

    primary_side_column: str = Field(default="signal")
    forward_returns_column: str = Field(default="forward_return")
    abstain_threshold: float = Field(default=0.0, ge=0.0)


class TrendScanParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Labeler"})

    price_column: str = Field(default="close")
    t_horizons: list[int] = Field(default_factory=lambda: [5, 10, 21])


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------


class TearsheetParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Output"})

    title: str = Field(default="Tearsheet")
    benchmark: str | None = Field(default=None, title="Benchmark equity series name")


class PublishMlflowParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Output"})

    experiment: str = Field(..., title="MLflow experiment name")
    run_name: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class AgentCrewaiParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Agent"})

    agent_spec: str = Field(..., title="Persisted AgentSpec name")
    prompt: str = Field(default="")
    persist_as_note: bool = Field(default=False)
    note_target_kind: Literal["graph", "run", "node_run", "label"] | None = Field(default=None)
    note_target_id: str | None = Field(default=None)


# ---------------------------------------------------------------------------
# Snippets
# ---------------------------------------------------------------------------


class SnippetPythonParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Transformation"})

    snippet_id: str | None = Field(default=None, title="Persisted snippet id")
    source: str | None = Field(default=None, title="Inline Python source")
    tier: Literal["tier1", "tier2"] = Field(default="tier1")
    preload: dict[str, Any] = Field(default_factory=dict)


class SnippetSqlParams(BaseModel):
    model_config = ConfigDict(json_schema_extra={"category": "Transformation"})

    snippet_id: str | None = Field(default=None, title="Persisted snippet id")
    sql: str | None = Field(default=None, title="Inline SQL")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


PARAMS_MODELS: dict[str, type[BaseModel]] = {
    "data.iceberg_scan": IcebergScanParams,
    "data.hudi_scan": HudiScanParams,
    "data.questdb_query": QuestDBQueryParams,
    "data.duckdb_sql": DuckDbSqlParams,
    "data.redpanda_subscribe": RedpandaSubscribeParams,
    "data.synthetic": SyntheticParams,
    "xform.resample": ResampleParams,
    "xform.winsorize": WinsorizeParams,
    "xform.neutralize": NeutralizeParams,
    "xform.rank": RankParams,
    "feature.technical": TechnicalParams,
    "feature.microstructure": MicrostructureParams,
    "feature.fracdiff": FracdiffParams,
    "feature.embedding": EmbeddingParams,
    "alpha.formulaic": FormulaicAlphaParams,
    "alpha.ml": AlphaMlParams,
    "alpha.combine": AlphaCombineParams,
    "model.sklearn": SklearnModelParams,
    "model.gbm": GbmModelParams,
    "model.torch": TorchModelParams,
    "model.rl": RlModelParams,
    "strategy.vbt_portfolio": VbtPortfolioParams,
    "strategy.lean_framework": LeanFrameworkParams,
    "strategy.hftbt_market_maker": HftbtMarketMakerParams,
    "math.gbm": GbmParams,
    "math.heston": HestonParams,
    "math.ou_jump": OuJumpParams,
    "math.regime_hmm": RegimeHmmParams,
    "label.triple_barrier": TripleBarrierParams,
    "label.meta": MetaLabelParams,
    "label.trend_scan": TrendScanParams,
    "out.tearsheet": TearsheetParams,
    "out.publish_mlflow": PublishMlflowParams,
    "agent.crewai": AgentCrewaiParams,
    "snippet.python": SnippetPythonParams,
    "snippet.sql": SnippetSqlParams,
}


def get_params_schema(alias: str) -> dict[str, Any] | None:
    """Return the JSON Schema for a NodeType's params model, or ``None``."""
    model = PARAMS_MODELS.get(alias)
    if model is None:
        return None
    try:
        return model.model_json_schema()
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "PARAMS_MODELS",
    "get_params_schema",
]
