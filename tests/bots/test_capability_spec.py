"""Phase 1: CapabilitySpec validators + Frequency enum."""
from __future__ import annotations

from decimal import Decimal

import pytest

from aqp_bots.spec import (
    AssetClass,
    BotSpec,
    CapabilitySpec,
    Frequency,
)


def test_capability_spec_defaults() -> None:
    caps = CapabilitySpec()
    assert caps.frequency == Frequency.MID
    assert caps.asset_classes == []
    assert caps.needs_numa_pinning is False
    assert caps.max_capital_usd == Decimal("0")


def test_hft_requires_numa_pinning() -> None:
    with pytest.raises(ValueError, match="needs_numa_pinning"):
        CapabilitySpec(
            frequency=Frequency.HFT,
            expected_p99_tick_to_trade_us=50,
            needs_numa_pinning=False,
        )


def test_hft_requires_p99_target() -> None:
    with pytest.raises(ValueError, match="expected_p99_tick_to_trade_us"):
        CapabilitySpec(
            frequency=Frequency.HFT,
            needs_numa_pinning=True,
            expected_p99_tick_to_trade_us=None,
        )


def test_hft_valid_passes() -> None:
    caps = CapabilitySpec(
        frequency=Frequency.HFT,
        asset_classes=[AssetClass.EQUITY],
        venues=["nasdaq"],
        needs_numa_pinning=True,
        expected_p99_tick_to_trade_us=50,
        needs_hugepages_mib=1024,
        needs_sr_iov=True,
        max_capital_usd=Decimal("5000000"),
    )
    assert caps.frequency == Frequency.HFT
    assert caps.needs_sr_iov is True


def test_botspec_accepts_capabilities_block() -> None:
    spec = BotSpec(
        name="HFT MM",
        kind="trading",
        strategy={"class": "X"},
        backtest={"engine": "vbt-pro:signals"},
        capabilities=CapabilitySpec(
            frequency=Frequency.HFT,
            needs_numa_pinning=True,
            expected_p99_tick_to_trade_us=50,
        ),
    )
    assert spec.capabilities is not None
    assert spec.capabilities.frequency == Frequency.HFT
