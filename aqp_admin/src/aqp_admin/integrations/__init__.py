"""HTTP brokers + identity wiring for the admin BFF.

The admin BFF talks to the AQP monolith + control plane over HTTP only
(per ``aqp_admin/AGENTS.md`` boundary #1: no ``aqp.*`` imports). These
brokers wrap every outbound call in:

- A fresh M2M bearer (Entra-primary) minted via
  :class:`aqp_platform_core.auth.M2MTokenBroker`.
- A short, redaction-aware retry policy that surfaces upstream
  failures as :class:`AdminBrokerError` so route handlers can map
  them to consistent envelopes.

Three brokers ship today:

- :class:`ControlPlaneBroker` — calls ``/manage/*`` on the CP.
- :class:`MonolithBroker` — calls the AQP monolith REST + DataMCP
  surface for tenancy / billing / accounts lookups.
- :class:`HaltBroker` — fan-out helper for the KillSwitch
  (``/admin/halt/all`` is wired through this).
"""
from __future__ import annotations

from aqp_admin.integrations.broker import (
    AdminBrokerError,
    ControlPlaneBroker,
    HaltBroker,
    MonolithBroker,
    build_default_brokers,
    get_brokers,
    reset_brokers,
)

__all__ = [
    "AdminBrokerError",
    "ControlPlaneBroker",
    "HaltBroker",
    "MonolithBroker",
    "build_default_brokers",
    "get_brokers",
    "reset_brokers",
]
