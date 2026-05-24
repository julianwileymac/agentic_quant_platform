"""Declarative ``BotSpec`` — the reproducible blueprint for any AQP bot.

A :class:`BotSpec` is the configuration contract every bot honours. It
is loaded from YAML or constructed in code and persisted (immutably,
hash-locked) in ``bot_versions`` so a historical run can always be
replayed against the exact spec it was built from.

Spec composition
----------------

```yaml
name: dual-ma-aapl
slug: dual-ma-aapl
kind: trading
description: Dual moving-average crossover bot on AAPL/MSFT.

universe:
  symbols: [AAPL.NASDAQ, MSFT.NASDAQ]

data_pipeline:
  preset: ohlcv-daily
  source: alpaca

strategy:
  class: FrameworkAlgorithm
  module_path: aqp.strategies.framework
  kwargs:
    universe_model: { class: StaticUniverse, kwargs: { symbols: [AAPL.NASDAQ] } }
    alpha_model: { class: DualMACrossoverAlpha, kwargs: { fast: 10, slow: 50 } }
    portfolio_model: { class: EqualWeightPortfolio }
    risk_model: { class: NoOpRiskModel }
    execution_model: { class: ImmediateExecutionModel }

backtest:
  engine: vbt-pro:signals
  kwargs:
    initial_cash: 100000.0

ml_models: []

agents:
  - spec_name: research.quant_vbtpro
    role: supervisor

rag:
  - levels: [l3]
    corpora: [strategies]
    per_level_k: 4

metrics:
  - { name: sharpe }
  - { name: max_drawdown }
  - { name: total_return }

risk:
  max_position_pct: 0.25
  max_daily_loss_pct: 0.02

deployment:
  target: paper_session
  brokerage: simulated
  feed: deterministic_replay
```

Snapshotting
------------

:meth:`snapshot_hash` returns the SHA256 of the canonical JSON form of
the spec (sorted keys, no whitespace). Persisting a spec via
:func:`aqp.bots.registry.persist_spec` writes a new :class:`BotVersion`
row whenever the hash changes. Existing versions are referenced by the
spec hash so identical specs collapse to one row.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# Re-export ``RAGRef`` from the agents package so spec authors can write
# ``rag:`` clauses with the exact same shape used by ``AgentSpec``.
from aqp.agents.spec import RAGRef

BotKind = Literal["trading", "research", "rl_trading"]
"""Subclass discriminator for :class:`aqp.bots.base.BaseBot`."""


# ---------------------------------------------------------------------------
# Capabilities (QuantBot Platform Phase 1 — enterprise extension)
# ---------------------------------------------------------------------------


class Frequency(StrEnum):
    """Latency / cadence class of a bot.

    Five canonical tiers, each maps to a specific K8s scheduling primitive
    in the operator (DaemonSet for HFT, StatefulSet for stateful mid-freq,
    Deployment for stateless, CronJob for EOD, Job/event-driven adapter
    for on-chain). HFT bots additionally require NUMA pinning + 1µs clock
    granularity (Commission Delegated Regulation (EU) 2017/574 RTS 25).
    """

    HFT = "hft"  # < 1ms tick-to-trade target
    MID = "mid"  # 1ms - 1s
    LOW = "low"  # 1s - 1min
    EOD = "eod"  # batch / daily rebalance
    EVENT = "event"  # event-driven (on-chain, news feed, scheduled trigger)


class AssetClass(StrEnum):
    """Asset class a bot trades. Used by the operator + risk policies."""

    EQUITY = "equity"
    FUTURE = "future"
    OPTION = "option"
    SPOT_CRYPTO = "spot_crypto"
    PERP = "perp"
    FX = "fx"
    ONCHAIN = "onchain"


class CapabilitySpec(BaseModel):
    """Hardware + scheduling capabilities the bot needs.

    Operator uses these to:

    1. Select the right K8s primitive (Deployment / StatefulSet /
       DaemonSet / CronJob / Job).
    2. Validate node assignment (NUMA pinning, HugePages, SR-IOV).
    3. Set Pod QoS class (Guaranteed for HFT, Burstable for others).
    4. Apply scheduling tolerations / affinity rules.

    A legacy bot (``kind=trading`` with no ``capabilities`` block) skips
    every check below and continues through the existing ``BotRuntime``
    path; capabilities is fully optional and additive.
    """

    frequency: Frequency = Frequency.MID
    asset_classes: list[AssetClass] = Field(default_factory=list)
    venues: list[str] = Field(default_factory=list)
    needs_gpu: bool = False
    needs_numa_pinning: bool = False
    needs_hugepages_mib: int = 0
    needs_sr_iov: bool = False
    expected_p99_tick_to_trade_us: int | None = None
    max_capital_usd: Decimal = Field(default=Decimal("0"))

    @model_validator(mode="after")
    def _hft_invariants(self) -> CapabilitySpec:
        """HFT bots MUST declare NUMA + p99 latency target.

        Mirrors blueprint §C.1: HFT pods land on dedicated nodes with
        ``cpuManagerPolicy: static`` and ``topologyManagerPolicy:
        single-numa-node``; without ``needs_numa_pinning=True`` the
        operator would schedule them on a shared node and silently
        violate the 1µs RTS 25 granularity requirement.
        """
        if self.frequency == Frequency.HFT:
            if not self.needs_numa_pinning:
                raise ValueError(
                    "Frequency.HFT requires needs_numa_pinning=True "
                    "(operator schedules HFT bots on dedicated NUMA nodes)"
                )
            if self.expected_p99_tick_to_trade_us is None:
                raise ValueError(
                    "Frequency.HFT requires expected_p99_tick_to_trade_us "
                    "(operator uses it to size the Prometheus alert SLO)"
                )
        return self


# ---------------------------------------------------------------------------
# Seven layer specs (composition model — blueprint §A.1)
# ---------------------------------------------------------------------------


class DataLayerSpec(BaseModel):
    """Market data ingestion configuration.

    A bot may declare zero or more adapters; each name resolves through
    the metaclass-registered :class:`MarketDataAdapter` registry. The
    legacy ``BotSpec.data_pipeline`` block remains the canonical
    historical-data source for backtest mode; this spec describes the
    live-data adapters consumed by the new ``BotKernel`` runtime.
    """

    adapters: list[str] = Field(default_factory=list)
    subscriptions: list[dict[str, Any]] = Field(default_factory=list)
    feature_store: dict[str, Any] | None = None
    normalization: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class StrategyLayerSpec(BaseModel):
    """Strategy composition: alpha → portfolio → execution algo.

    Distinct from the existing top-level ``BotSpec.strategy`` (which
    drives the legacy ``run_backtest_from_config`` / paper path).
    This block additionally lets a bot declare which execution algo
    (TWAP / VWAP / POV / IS / Iceberg) wraps the raw strategy signals
    when the kernel runtime is active.
    """

    alpha: dict[str, Any] | None = None
    portfolio_constructor: dict[str, Any] | None = None
    execution_algo: dict[str, Any] | None = None
    risk_overlay: dict[str, Any] | None = None
    warmup_bars: int = 0
    extras: dict[str, Any] = Field(default_factory=dict)


class RiskLayerSpec(BaseModel):
    """Pre-trade risk policy bindings.

    Layer-1 (in-bot, fast path) policies are listed by alias from the
    registered :class:`aqp_bots.risk.policies` module. Layer-2 (the
    out-of-band pre-trade risk service per 17 CFR § 240.15c3-5(d))
    is referenced via :attr:`risk_service_endpoint`.

    Reuses :class:`aqp_bots.spec.RiskSpec` for the position / drawdown /
    daily-loss caps; this layer carries the RTS 6 Article 15(1) and
    SEC 15c3-5 (c)(1) policy aliases.
    """

    layer1_policies: list[str] = Field(default_factory=list)
    risk_service_endpoint: str | None = None
    fail_open: bool = False
    price_collar_bps: int | None = None
    max_order_value_usd: Decimal | None = None
    max_order_qty: Decimal | None = None
    max_messages_per_second: int | None = None
    repeated_execution_throttle_ms: int | None = None
    instrument_allowlist: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)


class ExecutionLayerSpec(BaseModel):
    """Execution venue + order-routing configuration.

    Names registered :class:`ExecutionAdapter` aliases. The default
    SOR is ``latency_aware``; alternative routers register through
    the standard ``@register(name=..., kind="smart_order_router")``
    decorator.
    """

    adapters: list[str] = Field(default_factory=list)
    smart_order_router: str = "latency_aware"
    default_order_type: str = "limit"
    idempotency_lru_size: int = 4096
    reconcile_interval_ms: int = 500
    drop_copy_enabled: bool = False
    extras: dict[str, Any] = Field(default_factory=dict)


class StateLayerSpec(BaseModel):
    """Event-sourced state configuration.

    Production bots write through the partitioned ``bot_events`` table
    (Phase 4 — see migration 0061). The :attr:`mode` knob controls
    whether snapshots are written synchronously (durability-first) or
    asynchronously (HFT latency-first).
    """

    mode: Literal["sync", "async"] = "sync"
    snapshot_interval_seconds: int = 60
    event_store_enabled: bool = True
    replay_on_restart: bool = True
    extras: dict[str, Any] = Field(default_factory=dict)


class TelemetrySpec(BaseModel):
    """Observability configuration.

    Standard mode emits OTel traces / Prometheus metrics through
    :mod:`aqp.observability.tracing` (which delegates to
    ``rpi_k8s_sdk.tracing``). HFT mode swaps in the lock-free
    :class:`HFTSpanProcessor` and the microsecond Prometheus bucket
    boundaries.
    """

    otel_enabled: bool = True
    hft_mode: bool = False
    p99_alert_threshold_us: int | None = None
    metrics_namespace: str = "quantbot"
    log_correlation_id_field: str = "correlation_id"
    extras: dict[str, Any] = Field(default_factory=dict)


class LifecycleSpec(BaseModel):
    """Lifecycle hooks + graceful drain configuration.

    Operator finalizer respects :attr:`drain_timeout_seconds` (30s for
    HFT, 300s for everything else); :attr:`flatten_on_drain` flips the
    bot from cancel-only-on-shutdown to cancel + flatten.
    """

    drain_timeout_seconds: int = 300
    flatten_on_drain: bool = False
    warmup_timeout_seconds: int = 60
    health_check_path: str = "/healthz"
    readiness_check_path: str = "/readyz"
    environment: Literal["live", "paper", "backtest", "sim"] = "paper"
    extras: dict[str, Any] = Field(default_factory=dict)


class UniverseRef(BaseModel):
    """The trading universe a bot operates over.

    Two access modes are supported:

    - **Inline symbols** via :attr:`symbols` (a list of ``vt_symbol`` /
      ticker strings, parsed through :func:`aqp.core.types.Symbol.parse`).
    - **Universe model reference** via :attr:`model` (a registry-driven
      ``{class, module_path, kwargs}`` block; built lazily by the bot).
    """

    symbols: list[str] = Field(default_factory=list)
    model: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DataPipelineRef(BaseModel):
    """Pointer into :mod:`aqp.data.pipelines` for ingest/refresh of a bot's
    data plane.

    Two flavours:

    - **Preset** — names a row in
      :data:`aqp.data.dataset_presets.PRESETS` (e.g. ``ohlcv-daily``,
      ``options-chain-eod``). The bot dispatches the matching task in
      :mod:`aqp.tasks.dataset_preset_tasks` to materialise data into
      Iceberg.
    - **Inline** — a ``{class, module_path, kwargs}`` build-spec for an
      :class:`IngestionPipeline` subclass. Useful for bespoke sources.
    """

    preset: str | None = None
    source: str | None = None
    schedule: str | None = None
    inline: dict[str, Any] | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class MLDeploymentRef(BaseModel):
    """Reference to a row in the ``model_deployments`` table.

    The bot embeds these into ``strategy.kwargs.alpha_model.kwargs``
    (``deployment_id``) so :func:`aqp.backtest.runner.run_backtest_from_config`
    can attribute the run to the deployed model and retrieve its
    ``dataset_hash`` for lineage.
    """

    deployment_id: str
    role: str = "alpha"
    weight: float = 1.0


class BotAgentRef(BaseModel):
    """Reference to an :class:`aqp.agents.spec.AgentSpec` by name.

    The runtime resolves the spec via
    :func:`aqp.agents.registry.get_agent_spec` and runs it through
    :class:`aqp.agents.runtime.AgentRuntime` (the only sanctioned path).
    """

    spec_name: str
    role: str = "advisor"
    inputs_template: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class MetricRef(BaseModel):
    """One performance / evaluation metric.

    Bots aggregate metrics from two surfaces:

    - **Backtest summary** keys (``sharpe``, ``sortino``, ``max_drawdown``,
      ``total_return``, ``calmar``, …) — pulled out of
      :class:`aqp.backtest.engine.BacktestResult.summary`.
    - **Custom evaluators** — a ``{class, module_path, kwargs}``
      build-spec resolved through :func:`build_from_config` if
      :attr:`evaluator` is set.
    """

    name: str
    threshold: float | None = None
    direction: Literal["max", "min"] = "max"
    evaluator: dict[str, Any] | None = None


class RiskSpec(BaseModel):
    """Position / daily / drawdown caps consumed by
    :class:`aqp.risk.manager.RiskManager`.

    Defaults mirror the conservative caps surfaced through
    :class:`aqp.config.Settings`.
    """

    max_position_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_drawdown_pct: float | None = None
    max_concentration_pct: float = 0.3
    max_gross_exposure: float = 1.0
    extras: dict[str, Any] = Field(default_factory=dict)

    def to_runner_dict(self) -> dict[str, Any]:
        """Project to the dict shape consumed by :func:`aqp.trading.runner._risk_from_cfg`."""
        out: dict[str, Any] = {}
        if self.max_position_pct is not None:
            out["max_position_pct"] = float(self.max_position_pct)
        if self.max_daily_loss_pct is not None:
            out["max_daily_loss_pct"] = float(self.max_daily_loss_pct)
        if self.max_drawdown_pct is not None:
            out["max_drawdown_pct"] = float(self.max_drawdown_pct)
        out["max_concentration_pct"] = float(self.max_concentration_pct)
        out["max_gross_exposure"] = float(self.max_gross_exposure)
        out.update(self.extras)
        return out


DeploymentTargetKind = Literal["paper_session", "kubernetes", "backtest_only"]


class DeploymentTargetSpec(BaseModel):
    """Where + how the bot should run when ``deploy()`` is called.

    ``target=paper_session`` (Phase 1) launches the existing
    :class:`aqp.trading.session.PaperTradingSession` via the
    ``run_bot_paper`` Celery task. ``target=kubernetes`` (Phase 5)
    renders a manifest under ``aqp_platform/deploy/k8s/bots/`` that the cluster
    operator (Argo / KServe) consumes.
    """

    target: DeploymentTargetKind = "paper_session"
    brokerage: str | dict[str, Any] | None = None
    feed: str | dict[str, Any] | None = None
    initial_cash: float = 100000.0
    dry_run: bool = False
    heartbeat_seconds: int = 30
    max_bars: int | None = None
    namespace: str = "aqp-bots"
    image: str | None = None
    resources: dict[str, Any] = Field(default_factory=dict)
    extras: dict[str, Any] = Field(default_factory=dict)


class RLExperimentRef(BaseModel):
    """Reference to a registered :class:`RLExperimentSpec` (Phase 8).

    Lets a bot declare that its strategy is *driven by* a trained RL
    policy rather than a hand-coded ``Strategy`` subclass. When set
    on :attr:`BotSpec.rl_experiment_ref`, the bot's lifecycle methods
    route through :class:`aqp.rl.runtime.RLRuntime` for train /
    evaluate / paper / replay (instead of through
    ``run_backtest_from_config`` / ``build_session_from_config``).

    Carrying just the slug + (optional) checkpoint keeps the bot
    spec hash-stable across RL training runs — the bot version
    snapshot doesn't churn every time a new RL run completes.
    """

    slug: str = Field(description="Slug of the registered RLExperimentSpec.")
    checkpoint: str | None = Field(
        default=None,
        description="Specific checkpoint path. Omit to use the latest from MLflow.",
    )
    deterministic: bool = Field(
        default=True,
        description="Pass to RLRuntime.evaluate / paper for deterministic rollout.",
    )
    extras: dict[str, Any] = Field(default_factory=dict)


class BotSpec(BaseModel):
    """Declarative blueprint for one bot.

    ``kind`` selects the subclass (``TradingBot`` / ``ResearchBot`` /
    ``RLTradingBot``) at instantiation time via
    :func:`aqp.bots.base.build_bot`.
    """

    name: str
    slug: str = ""
    kind: BotKind = "trading"
    description: str = ""

    universe: UniverseRef = Field(default_factory=UniverseRef)
    data_pipeline: DataPipelineRef | None = None

    strategy: dict[str, Any] | None = None
    backtest: dict[str, Any] | None = None
    # Phase 8 of the agentic-RL rollout: declare that the bot is
    # driven by a trained RL policy instead of a hand-coded
    # ``Strategy``. The runtime routes through
    # :class:`aqp.rl.runtime.RLRuntime` whenever this is set.
    rl_experiment_ref: RLExperimentRef | None = None

    ml_models: list[MLDeploymentRef] = Field(default_factory=list)
    agents: list[BotAgentRef] = Field(default_factory=list)
    rag: list[RAGRef] = Field(default_factory=list)
    metrics: list[MetricRef] = Field(default_factory=list)
    risk: RiskSpec = Field(default_factory=RiskSpec)
    deployment: DeploymentTargetSpec = Field(default_factory=DeploymentTargetSpec)

    # QuantBot Platform Phase 1 — opt-in capability + layer specs.
    # When ``capabilities`` is None the legacy BotRuntime path runs
    # unchanged; when set, BotRuntime._run_with_kernel() (Phase 2)
    # composes the layered runtime instead.
    capabilities: CapabilitySpec | None = None
    data_layer: DataLayerSpec | None = None
    strategy_layer: StrategyLayerSpec | None = None
    risk_layer: RiskLayerSpec | None = None
    execution_layer: ExecutionLayerSpec | None = None
    state_layer: StateLayerSpec | None = None
    telemetry: TelemetrySpec | None = None
    lifecycle: LifecycleSpec | None = None

    annotations: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------ validation

    @model_validator(mode="after")
    def _ensure_slug(self) -> BotSpec:
        if not self.slug:
            self.slug = _slugify(self.name) if self.name else ""
        else:
            self.slug = _slugify(self.slug)
        return self

    @field_validator("agents", mode="before")
    @classmethod
    def _coerce_agents(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        out: list[Any] = []
        for item in value:
            if isinstance(item, str):
                out.append({"spec_name": item})
            else:
                out.append(item)
        return out

    @field_validator("metrics", mode="before")
    @classmethod
    def _coerce_metrics(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        out: list[Any] = []
        for item in value:
            if isinstance(item, str):
                out.append({"name": item})
            else:
                out.append(item)
        return out

    @field_validator("rag", mode="before")
    @classmethod
    def _coerce_rag(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        return list(value)

    @field_validator("ml_models", mode="before")
    @classmethod
    def _coerce_ml_models(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        out: list[Any] = []
        for item in value:
            if isinstance(item, str):
                out.append({"deployment_id": item})
            else:
                out.append(item)
        return out

    # ------------------------------------------------------------------ snapshotting

    def snapshot_hash(self) -> str:
        """SHA256 over the canonical JSON form (sorted keys, no whitespace)."""
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------ YAML helpers

    @classmethod
    def from_yaml_path(cls, path: str) -> BotSpec:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def from_yaml_str(cls, content: str) -> BotSpec:
        data = yaml.safe_load(content) or {}
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)

    # ------------------------------------------------------------------ kind helpers

    def is_trading(self) -> bool:
        return self.kind == "trading"

    def is_research(self) -> bool:
        return self.kind == "research"

    def universe_symbols(self) -> list[str]:
        """Best-effort flat list of ``vt_symbol`` strings.

        Falls back to ``strategy.kwargs.universe_model.kwargs.symbols``
        when the spec didn't carry an inline universe — this keeps bots
        compatible with the dozens of strategy YAMLs that already encode
        their own static universe block.
        """
        if self.universe.symbols:
            return list(self.universe.symbols)
        cfg = self.strategy or {}
        kwargs = cfg.get("kwargs", {}) if isinstance(cfg, dict) else {}
        uni = kwargs.get("universe_model", {}) if isinstance(kwargs, dict) else {}
        uni_kw = uni.get("kwargs", {}) if isinstance(uni, dict) else {}
        symbols = uni_kw.get("symbols") if isinstance(uni_kw, dict) else None
        if isinstance(symbols, list):
            return [str(s) for s in symbols]
        return []


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]


def load_specs_from_dir(dir_path: str, *, suffix: str = ".yaml") -> Iterable[BotSpec]:
    """Yield every bot spec yaml under ``dir_path`` (recursively).

    Recursion lets the on-disk layout reflect the kind:

    - ``configs/bots/trading/<slug>.yaml`` for :class:`TradingBot`
    - ``configs/bots/research/<slug>.yaml` for :class:`ResearchBot`
    """
    from pathlib import Path

    root = Path(dir_path)
    if not root.exists():
        return
    for p in sorted(root.rglob(f"*{suffix}")):
        try:
            yield BotSpec.from_yaml_path(str(p))
        except Exception:  # noqa: BLE001
            continue


__all__ = [
    "AssetClass",
    "BotAgentRef",
    "BotKind",
    "BotSpec",
    "CapabilitySpec",
    "DataLayerSpec",
    "DataPipelineRef",
    "DeploymentTargetKind",
    "DeploymentTargetSpec",
    "ExecutionLayerSpec",
    "Frequency",
    "LifecycleSpec",
    "MLDeploymentRef",
    "MetricRef",
    "RAGRef",
    "RLExperimentRef",
    "RiskLayerSpec",
    "RiskSpec",
    "StateLayerSpec",
    "StrategyLayerSpec",
    "TelemetrySpec",
    "UniverseRef",
    "load_specs_from_dir",
]
