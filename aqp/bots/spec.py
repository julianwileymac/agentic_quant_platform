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
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# Re-export ``RAGRef`` from the agents package so spec authors can write
# ``rag:`` clauses with the exact same shape used by ``AgentSpec``.
from aqp.agents.spec import RAGRef

BotKind = Literal["trading", "research"]
"""Subclass discriminator for :class:`aqp.bots.base.BaseBot`."""


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
    renders a manifest under ``deploy/k8s/bots/`` that the cluster
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


class BotSpec(BaseModel):
    """Declarative blueprint for one bot.

    ``kind`` selects the subclass (``TradingBot`` vs ``ResearchBot``) at
    instantiation time via :func:`aqp.bots.base.build_bot`.
    """

    name: str
    slug: str = ""
    kind: BotKind = "trading"
    description: str = ""

    universe: UniverseRef = Field(default_factory=UniverseRef)
    data_pipeline: DataPipelineRef | None = None

    strategy: dict[str, Any] | None = None
    backtest: dict[str, Any] | None = None

    ml_models: list[MLDeploymentRef] = Field(default_factory=list)
    agents: list[BotAgentRef] = Field(default_factory=list)
    rag: list[RAGRef] = Field(default_factory=list)
    metrics: list[MetricRef] = Field(default_factory=list)
    risk: RiskSpec = Field(default_factory=RiskSpec)
    deployment: DeploymentTargetSpec = Field(default_factory=DeploymentTargetSpec)

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
    "BotAgentRef",
    "BotKind",
    "BotSpec",
    "DataPipelineRef",
    "DeploymentTargetKind",
    "DeploymentTargetSpec",
    "MLDeploymentRef",
    "MetricRef",
    "RAGRef",
    "RiskSpec",
    "UniverseRef",
    "load_specs_from_dir",
]
