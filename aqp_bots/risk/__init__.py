"""QuantBot Platform risk layer — RTS 6 + SEC 15c3-5 compliant.

Three pillars:

1. **Layer-1 (in-bot, fast path)** — :class:`PreTradeRiskEngine` extends
   the existing :class:`aqp.risk.manager.RiskManager` v2 path with the
   RTS 6 Article 15(1) checks (price collar, max order value/volume,
   message rate, repeated-execution throttle, instrument allowlist).
2. **Layer-2 (out-of-band)** — :mod:`aqp_bots.risk.service` exposes a
   FastAPI sub-app on a separate Pod (per 17 CFR § 240.15c3-5(d) which
   requires the risk controls to be "under the direct and exclusive
   control of the broker or dealer").
3. **Kill switch v2** — :mod:`aqp_bots.risk.kill_switch_v2` extends the
   existing single global key from :mod:`aqp.risk.kill_switch` with
   three scopes (bot / fleet / platform) and a redundant Redis polling
   channel that survives operator outages.

The :mod:`aqp_bots.risk.reg` subpackage carries the explicit regulatory
crosswalks (RTS 6 Art. 15, SEC 15c3-5 (c)(1), RTS 6 Art. 9 validation
report, Art. 6 conformance, Art. 10 stress test). These are engineering
crosswalks, NOT legal advice — see blueprint caveat #5.
"""
from __future__ import annotations

from aqp_bots.risk.circuit import CircuitBreaker, CircuitState
from aqp_bots.risk.engine import PreTradeRiskEngine, PreTradeVerdict
from aqp_bots.risk.kill_switch_v2 import (
    KillSwitchScope,
    KillSwitchV2,
    engage_scoped,
    is_engaged_scoped,
    release_scoped,
)
from aqp_bots.risk.policies import (
    BuyingPowerPolicy,
    FatFingerPolicy,
    InstrumentAllowlistPolicy,
    MaxMessagesPerSecondPolicy,
    MaxOrderValuePolicy,
    MaxOrderVolumePolicy,
    PolicyVerdict,
    PreTradePolicy,
    PriceCollarPolicy,
    RepeatedExecutionThrottlePolicy,
    VolatilityCircuitBreakerPolicy,
)

__all__ = [
    "BuyingPowerPolicy",
    "CircuitBreaker",
    "CircuitState",
    "FatFingerPolicy",
    "InstrumentAllowlistPolicy",
    "KillSwitchScope",
    "KillSwitchV2",
    "MaxMessagesPerSecondPolicy",
    "MaxOrderValuePolicy",
    "MaxOrderVolumePolicy",
    "PolicyVerdict",
    "PreTradePolicy",
    "PreTradeRiskEngine",
    "PreTradeVerdict",
    "PriceCollarPolicy",
    "RepeatedExecutionThrottlePolicy",
    "VolatilityCircuitBreakerPolicy",
    "engage_scoped",
    "is_engaged_scoped",
    "release_scoped",
]
