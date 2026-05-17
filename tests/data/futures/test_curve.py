"""Tests for the continuous futures-curve constructor.

Pure-Python stitching is tested with hand-built snapshot sequences so
the suite stays hermetic (no DB / no pyarrow required for the core
stitching logic). The pyarrow ``to_arrow`` helper is skipped when the
optional dep is missing.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from aqp.data.futures.curve import (
    DateBasedRoll,
    FuturesCurve,
    FuturesCurveSnapshot,
    OpenInterestRoll,
    VolumeBasedRoll,
    stitch_curve,
)


def _snap(
    *,
    contract: str,
    expiry: date,
    snapshot: date,
    price: float,
    volume: float | None = None,
    oi: float | None = None,
) -> FuturesCurveSnapshot:
    return FuturesCurveSnapshot(
        root_symbol="ES",
        expiry=expiry,
        snapshot_date=snapshot,
        contract_symbol=contract,
        price=price,
        volume=volume,
        open_interest=oi,
    )


def _curve_two_contracts():
    """ES front Mar-26 expires 2026-03-20; back Jun-26 expires 2026-06-19.

    Five business days, with volume crossing on day 3 -- triggers
    :class:`VolumeBasedRoll` exactly on 2026-03-18.
    """
    base = date(2026, 3, 16)
    front_expiry = date(2026, 3, 20)
    back_expiry = date(2026, 6, 19)
    snaps = []
    # Pre-roll: front carries higher volume on days 1-2
    for i, vol in enumerate([(100, 30), (90, 40), (80, 150), (70, 200), (60, 250)]):
        d = base + timedelta(days=i)
        snaps.append(
            _snap(
                contract="ESH26",
                expiry=front_expiry,
                snapshot=d,
                price=5100.0 - i,
                volume=vol[0],
                oi=10_000 - 1_000 * i,
            )
        )
        snaps.append(
            _snap(
                contract="ESM26",
                expiry=back_expiry,
                snapshot=d,
                price=5110.0 - i,  # backwardation
                volume=vol[1],
                oi=2_000 + 2_000 * i,
            )
        )
    return FuturesCurve(root_symbol="ES", snapshots=snaps)


def test_volume_based_roll_triggers_on_crossover():
    curve = _curve_two_contracts()
    rows, rolls = stitch_curve(curve, rule=VolumeBasedRoll(), adjustment="none")
    assert len(rows) == 5
    # Roll happens on day 3 (index 2) when back-month volume 150 > front-month 80
    assert len(rolls) == 1
    assert rolls[0].snapshot_date == date(2026, 3, 18)
    assert rolls[0].from_contract == "ESH26"
    assert rolls[0].to_contract == "ESM26"
    # Days 0-1 reference the front contract; day 2 onwards references the back.
    assert rows[0].contract_symbol == "ESH26"
    assert rows[1].contract_symbol == "ESH26"
    assert rows[2].contract_symbol == "ESM26"
    assert rows[3].contract_symbol == "ESM26"


def test_back_adjusted_eliminates_roll_gap():
    """Back-adjustment shifts pre-roll prices up so the stitched series is continuous."""
    curve = _curve_two_contracts()
    rows, rolls = stitch_curve(
        curve, rule=VolumeBasedRoll(), adjustment="back_adjusted"
    )
    # The roll on day 2 -- the raw gap was from front=5098 to back=5108
    # so additive_offset = 5108 - 5098 = +10. All prior days get bumped +10.
    pre_roll = [r for r in rows if not r.rolled and r.snapshot_date < rolls[0].snapshot_date]
    # Day 0 raw price was 5100, adjusted should be 5110.
    assert pre_roll[0].price == pytest.approx(5110.0, abs=1e-6)
    # Day before roll: raw 5099, adjusted 5109.
    assert pre_roll[1].price == pytest.approx(5109.0, abs=1e-6)


def test_ratio_adjustment_multiplies():
    """Ratio adjustment scales pre-roll prices by new/old multiplier."""
    curve = _curve_two_contracts()
    rows, rolls = stitch_curve(curve, rule=VolumeBasedRoll(), adjustment="ratio")
    # Day 2 (roll): old price 5098, new price 5108. Ratio = 5108/5098.
    expected_factor = 5108.0 / 5098.0
    pre_roll = [r for r in rows if not r.rolled and r.snapshot_date < rolls[0].snapshot_date]
    assert pre_roll[0].price == pytest.approx(5100.0 * expected_factor, rel=1e-6)
    assert pre_roll[0].adjustment_factor == pytest.approx(expected_factor, rel=1e-9)


def test_date_based_roll():
    """Date rule rolls within ``days_before_expiry`` of the front expiry."""
    curve = _curve_two_contracts()
    rows, rolls = stitch_curve(
        curve, rule=DateBasedRoll(days_before_expiry=2), adjustment="none"
    )
    # Front expires 2026-03-20. With threshold=2, the roll happens on
    # the first snapshot where (expiry - today) <= 2 -- that's 2026-03-18.
    assert len(rolls) == 1
    assert rolls[0].snapshot_date == date(2026, 3, 18)


def test_open_interest_roll():
    """OI rule rolls when back-month OI exceeds front-month."""
    curve = _curve_two_contracts()
    rows, rolls = stitch_curve(curve, rule=OpenInterestRoll(), adjustment="none")
    # On day 3 front_oi=7000, back_oi=8000 -> roll triggers
    assert len(rolls) >= 1


def test_empty_curve_returns_empty():
    """Empty input emits empty output, not an exception."""
    rows, rolls = stitch_curve(
        FuturesCurve(root_symbol="ES", snapshots=[]),
        rule=VolumeBasedRoll(),
    )
    assert rows == []
    assert rolls == []


def test_only_expired_snapshots_skipped():
    """Snapshots after their own contract's expiry are ignored."""
    snaps = [
        _snap(
            contract="ESH26",
            expiry=date(2026, 3, 20),
            snapshot=date(2026, 3, 25),  # already expired
            price=5100,
            volume=100,
        ),
    ]
    rows, rolls = stitch_curve(
        FuturesCurve(root_symbol="ES", snapshots=snaps), rule=VolumeBasedRoll()
    )
    assert rows == []
    assert rolls == []


def test_volume_rule_does_not_roll_when_volume_missing():
    """Roll rules return False when key fields are None (don't accidentally roll)."""
    rule = VolumeBasedRoll()
    front = _snap(
        contract="ESH26",
        expiry=date(2026, 3, 20),
        snapshot=date(2026, 3, 16),
        price=5100,
        volume=None,
    )
    back = _snap(
        contract="ESM26",
        expiry=date(2026, 6, 19),
        snapshot=date(2026, 3, 16),
        price=5108,
        volume=None,
    )
    assert rule.should_roll(front=front, next_contract=back, as_of=date(2026, 3, 16)) is False


def test_stitched_arrow_table_when_pyarrow_present():
    """The to-arrow helper is exercised only when pyarrow is installed."""
    pa = pytest.importorskip("pyarrow")
    from aqp.data.futures.curve import stitched_to_arrow

    curve = _curve_two_contracts()
    rows, _ = stitch_curve(curve, rule=VolumeBasedRoll(), adjustment="back_adjusted")
    tbl = stitched_to_arrow(
        rows,
        root_symbol="ES",
        rule_name="volume",
        adjustment="back_adjusted",
    )
    assert isinstance(tbl, pa.Table)
    # All columns the Iceberg sink expects must be present.
    for required in (
        "root_symbol",
        "snapshot_date",
        "price",
        "raw_price",
        "contract_symbol",
        "contract_expiry",
        "adjustment_factor",
        "rolled",
        "rule_name",
        "adjustment_mode",
        "stitched_at",
    ):
        assert required in tbl.column_names
