"""Out-of-band pre-trade risk service.

Per 17 CFR § 240.15c3-5(d), the financial-risk pre-trade controls
must be "under the direct and exclusive control of the broker or
dealer". The in-bot Layer-1 engine (:class:`PreTradeRiskEngine`) is
operated by the bot itself for ultra-low latency, but it cannot
satisfy (d) on its own — the controls must also be exercised by an
operator-controlled out-of-band process.

This module exposes that out-of-band process as a FastAPI sub-app:

- ``POST /pretrade/check`` — synchronous Layer-2 check
- ``GET /pretrade/policies`` — list configured policies
- ``GET /healthz`` — liveness
- ``GET /metrics`` — Prometheus exposition

In production this app runs as a separate K8s Deployment with its own
ServiceAccount and RBAC scope; the in-bot engine forwards every order
to it before placement when ``RiskLayerSpec.risk_service_endpoint`` is
set.
"""
from __future__ import annotations

from aqp_bots.risk.service.app import (
    PreTradeCheckRequest,
    PreTradeCheckResponse,
    create_risk_service_app,
)

__all__ = [
    "PreTradeCheckRequest",
    "PreTradeCheckResponse",
    "create_risk_service_app",
]
