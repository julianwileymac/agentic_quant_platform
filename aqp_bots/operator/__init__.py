"""QuantBot Platform Kubernetes Operator (kopf-based).

Reconciles 9 CRDs in the ``quantbot.io/v1`` API group:

- ``Bot`` — one running bot instance (the atomic unit).
- ``Strategy`` — versioned, reusable strategy definition.
- ``RiskPolicy`` — RTS 6 / 15c3-5 policy attached to one or more bots.
- ``MarketDataFeed`` — venue feed config (FIX/WS/REST + credentials).
- ``ExecutionVenue`` — venue execution + drop-copy session config.
- ``BacktestJob`` — backtest / walk-forward / parameter-sweep.
- ``BotFleet`` — logical group of bots with shared policy.
- ``CanaryRollout`` — Argo Rollouts canary spec.
- ``KillSwitch`` — bot/fleet/platform kill switch.

The operator runs as a separate Kubernetes Deployment (see
``aqp_platform/deployments/kubernetes/bots-operator/``) with its own
ServiceAccount + ClusterRole + ValidatingWebhookConfiguration.

Hard rules preserved (see :mod:`aqp_bots.operator.handlers`):

- Rule 14: All Bot lifecycle ops route through :class:`BotRuntime` via
  the Bot CR's underlying Pod entrypoint, never bypassed by the operator.
- Rule 15: Bot spec snapshots go through ``persist_spec()`` — operator
  never mutates ``bot_versions`` directly.
- Rule 45: Workload ops (start/stop/scale/restart) route through
  :class:`aqp_platform_core.WorkloadRuntime`.
"""
from __future__ import annotations

from aqp_bots.operator.crds import (
    BacktestJobCR,
    BotCR,
    BotFleetCR,
    CanaryRolloutCR,
    ExecutionVenueCR,
    KillSwitchCR,
    MarketDataFeedCR,
    RiskPolicyCR,
    StrategyCR,
)
from aqp_bots.operator.labels import bot_labels
from aqp_bots.operator.render import render_bot_workload

__all__ = [
    "BacktestJobCR",
    "BotCR",
    "BotFleetCR",
    "CanaryRolloutCR",
    "ExecutionVenueCR",
    "KillSwitchCR",
    "MarketDataFeedCR",
    "RiskPolicyCR",
    "StrategyCR",
    "bot_labels",
    "render_bot_workload",
]
