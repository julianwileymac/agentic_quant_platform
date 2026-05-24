"""Phase 5: RTS 6 Art. 15(1) policies + SEC 15c3-5 (c)(1) mappings."""
from __future__ import annotations

from decimal import Decimal

import pytest

from aqp_bots.risk.engine import PreTradeRiskEngine
from aqp_bots.risk.policies import (
    InstrumentAllowlistPolicy,
    MaxMessagesPerSecondPolicy,
    MaxOrderValuePolicy,
    MaxOrderVolumePolicy,
    PreTradeContext,
    PriceCollarPolicy,
    RepeatedExecutionThrottlePolicy,
)
from aqp_bots.risk.reg.rts6 import RTS6_ART_15_MAPPING, rts6_required_policies
from aqp_bots.risk.reg.rule_15c3_5 import RULE_15C3_5_C1_MAPPING
from aqp_bots.schemas.trading import NewOrder, Side, TimeInForce


def _order(**overrides) -> NewOrder:
    base = {
        "venue": "test",
        "symbol": "TEST.NASDAQ",
        "side": Side.BUY,
        "quantity": Decimal("100"),
        "order_type": "limit",
        "time_in_force": TimeInForce.GTC,
        "limit_price": Decimal("100"),
        "client_order_id": "coid",
        "strategy_id": "s1",
    }
    base.update(overrides)
    return NewOrder(**base)


# ----- Article 15(1)(a) — price collar -----


def test_price_collar_blocks_outside_collar() -> None:
    p = PriceCollarPolicy(max_bps=100)  # 1%
    ctx = PreTradeContext(mark_price=Decimal("100"))
    order = _order(limit_price=Decimal("105"))  # 500 bps off
    v = p.evaluate(order, ctx)
    assert v.severity == "block"
    assert "RTS 6 Art. 15(1)(a)" in v.citation


def test_price_collar_allows_inside_collar() -> None:
    p = PriceCollarPolicy(max_bps=100)
    ctx = PreTradeContext(mark_price=Decimal("100"))
    order = _order(limit_price=Decimal("100.5"))  # 50 bps
    assert p.evaluate(order, ctx).severity == "allow"


# ----- Article 15(1)(b) — max order value -----


def test_max_order_value_blocks_when_exceeded() -> None:
    p = MaxOrderValuePolicy(max_value_usd=Decimal("1000"))
    ctx = PreTradeContext(mark_price=Decimal("100"))
    order = _order(quantity=Decimal("100"))  # notional 10_000
    v = p.evaluate(order, ctx)
    assert v.severity == "block"
    assert "Art. 15(1)(b)" in v.citation


# ----- Article 15(1)(c) — max order volume -----


def test_max_order_volume_blocks_when_exceeded() -> None:
    p = MaxOrderVolumePolicy(max_qty=Decimal("10"))
    v = p.evaluate(_order(quantity=Decimal("100")), PreTradeContext())
    assert v.severity == "block"
    assert "Art. 15(1)(c)" in v.citation


# ----- Article 15(1)(d) — max messages per second -----


def test_max_messages_per_second_blocks_when_rate_exceeded() -> None:
    p = MaxMessagesPerSecondPolicy(max_rate=3)
    ctx = PreTradeContext()
    assert p.evaluate(_order(), ctx).severity == "allow"
    assert p.evaluate(_order(), ctx).severity == "allow"
    assert p.evaluate(_order(), ctx).severity == "allow"
    blocked = p.evaluate(_order(), ctx)
    assert blocked.severity == "block"
    assert "Art. 15(1)(d)" in blocked.citation


# ----- Article 15(3) — repeated execution throttle -----


def test_repeated_execution_throttle_blocks_rapid_repeats() -> None:
    p = RepeatedExecutionThrottlePolicy(min_interval_ms=500)
    ctx = PreTradeContext()
    assert p.evaluate(_order(), ctx).severity == "allow"
    # Same (strategy_id, symbol) within 500ms.
    blocked = p.evaluate(_order(), ctx)
    assert blocked.severity == "block"
    assert "Art. 15(3)" in blocked.citation


# ----- Article 15(5) — instrument allowlist -----


def test_instrument_allowlist_blocks_unlisted() -> None:
    p = InstrumentAllowlistPolicy(allowlist=["ONLY.NYSE"])
    v = p.evaluate(_order(symbol="OTHER.NASDAQ"), PreTradeContext())
    assert v.severity == "block"
    assert "Art. 15(5)" in v.citation


def test_instrument_allowlist_allows_listed() -> None:
    p = InstrumentAllowlistPolicy(allowlist=["TEST.NASDAQ"])
    assert p.evaluate(_order(), PreTradeContext()).severity == "allow"


# ----- Engine composition -----


def test_engine_fails_fast_on_hard_block() -> None:
    engine = PreTradeRiskEngine(
        policies=[
            PriceCollarPolicy(max_bps=10),  # tight
            MaxOrderValuePolicy(max_value_usd=Decimal("1000000")),  # generous
        ],
        check_kill_switch=False,
        check_legacy_risk_manager=False,
    )
    ctx = PreTradeContext(mark_price=Decimal("100"))
    order = _order(limit_price=Decimal("200"))  # outside collar
    verdict = engine.evaluate(order, ctx)
    assert not verdict.passed
    assert verdict.severity == "block"
    assert verdict.citations  # at least one citation present


# ----- Regulatory mapping completeness -----


def test_rts6_required_policies_cover_all_art_15_subparagraphs() -> None:
    required = set(rts6_required_policies())
    # Every policy class in the canonical Art. 15 mapping must be required.
    for cls_name in RTS6_ART_15_MAPPING.keys():
        assert cls_name in required, f"{cls_name} missing from required policies"


def test_15c3_5_mapping_covers_core_policies() -> None:
    # The 15c3-5 crosswalk must reference the financial-risk policies.
    must = {"PriceCollarPolicy", "MaxOrderValuePolicy", "MaxOrderVolumePolicy"}
    assert must.issubset(set(RULE_15C3_5_C1_MAPPING.keys()))
