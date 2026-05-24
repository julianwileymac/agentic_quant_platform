"""Pydantic mirrors of the 9 CRDs in ``quantbot.io/v1``.

Each CR's ``.spec`` field is validated through these Pydantic models;
they're the single source of truth for the YAML CRD schemas under
``aqp_bots/operator/crds/yaml/`` and for the operator's reconciliation
logic.

Pattern: each ``*CR`` Pydantic class is the *full* CR shape — including
``apiVersion``, ``kind``, ``metadata``, ``spec``, and ``status`` — so
the operator can deserialize a raw k8s object verbatim.
"""
from __future__ import annotations

from aqp_bots.operator.crds.backtestjob_cr import BacktestJobCR
from aqp_bots.operator.crds.bot_cr import BotCR
from aqp_bots.operator.crds.botfleet_cr import BotFleetCR
from aqp_bots.operator.crds.canaryrollout_cr import CanaryRolloutCR
from aqp_bots.operator.crds.executionvenue_cr import ExecutionVenueCR
from aqp_bots.operator.crds.killswitch_cr import KillSwitchCR
from aqp_bots.operator.crds.marketdatafeed_cr import MarketDataFeedCR
from aqp_bots.operator.crds.riskpolicy_cr import RiskPolicyCR
from aqp_bots.operator.crds.strategy_cr import StrategyCR

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
]
