"""Bot — the smallest self-contained, deployable unit on AQP.

A :class:`Bot` aggregates everything required to research, evaluate, and
deploy an algorithmic trading automation: a data universe, a data
ingestion pipeline preset, a strategy graph, a backtest engine, optional
ML model deployments, optional spec-driven agents, an evaluation profile,
risk limits, and a deployment target.

Bots live under a :class:`aqp.persistence.models_tenancy.Project` (the
ORM row carries ``project_id`` via :class:`ProjectScopedMixin`). Within a
project, bots are uniquely identified by their slug.

Two subclasses ship in tree:

- :class:`TradingBot` — strategy + backtest + paper / live deployment.
- :class:`ResearchBot` — agents + RAG + chat surface; backtest optional.

The runtime (:class:`BotRuntime`) is the single entry point for executing
a bot end-to-end. It snapshots the spec into ``bot_versions`` (immutable,
hash-locked) and emits progress through :mod:`aqp.tasks._progress` so
existing ``/chat/stream/<task_id>`` consumers light up unchanged.

Hard rules
----------

- Bot agent calls go through :class:`aqp.agents.runtime.AgentRuntime`;
  :class:`BotRuntime` never calls ``router_complete`` directly.
- Bot RAG access goes through :class:`aqp.rag.HierarchicalRAG` via the
  agent's ``rag:`` clause.
- Bot data loading uses :class:`aqp.data.pipelines.runner.IngestionPipeline`
  and ``iceberg_catalog.append_arrow``; never raw PyIceberg.
- Strategy / engine / model construction goes through
  :func:`aqp.core.registry.build_from_config`.
"""
from __future__ import annotations

from aqp.bots.base import BaseBot, build_bot, load_bot_from_spec
from aqp.bots.deploy import (
    BotDeploymentResult,
    DeploymentDispatcher,
    DeploymentTarget,
    PaperSessionTarget,
)
from aqp.bots.registry import (
    add_spec,
    get_bot_spec,
    list_bot_specs,
    persist_spec,
    register_bot_spec,
    reload_yaml_dir,
    replay_spec_version,
)
from aqp.bots.research_bot import ResearchBot
from aqp.bots.runtime import BotRunResult, BotRuntime
from aqp.bots.spec import (
    BotAgentRef,
    BotKind,
    BotSpec,
    DataPipelineRef,
    DeploymentTargetSpec,
    MetricRef,
    MLDeploymentRef,
    RiskSpec,
    UniverseRef,
)
from aqp.bots.trading_bot import TradingBot

__all__ = [
    "BaseBot",
    "BotAgentRef",
    "BotDeploymentResult",
    "BotKind",
    "BotRunResult",
    "BotRuntime",
    "BotSpec",
    "DataPipelineRef",
    "DeploymentDispatcher",
    "DeploymentTarget",
    "DeploymentTargetSpec",
    "MLDeploymentRef",
    "MetricRef",
    "PaperSessionTarget",
    "ResearchBot",
    "RiskSpec",
    "TradingBot",
    "UniverseRef",
    "add_spec",
    "build_bot",
    "get_bot_spec",
    "list_bot_specs",
    "load_bot_from_spec",
    "persist_spec",
    "register_bot_spec",
    "reload_yaml_dir",
    "replay_spec_version",
]
