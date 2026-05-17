"""Continuous futures-curve construction.

Builds a stitched, distortion-free continuous time series from a set of
expiring :class:`aqp.persistence.models_instruments.InstrumentFuture` rows
and per-day :class:`aqp.persistence.models_macro.FuturesCurveRow`
snapshots. Three roll-rule strategies are provided:

* :class:`VolumeBasedRoll` -- transition to the next contract on the
  first day where the next contract trades higher volume than the
  expiring one
* :class:`DateBasedRoll` -- transition exactly ``days_before_expiry``
  business days before the front-month expiry
* :class:`OpenInterestRoll` -- transition when the next contract's open
  interest exceeds the front-month's

The output supports three adjustment modes:

* ``"none"`` -- no adjustment (raw stitched series, has discontinuities
  at every roll)
* ``"back_adjusted"`` -- additive back-adjustment so the latest contract
  price is preserved and older history shifts to eliminate jumps
* ``"ratio"`` -- multiplicative back-adjustment (each roll multiplies
  pre-roll prices by ``new_price / old_price``)

The stitched series can be written to Iceberg via
:func:`aqp.data.iceberg_catalog.append_arrow` -- the helper here just
returns an Arrow ``Table`` so callers stay in control of the medallion
namespace and metadata block.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date as dateType, datetime
from typing import TYPE_CHECKING, Any, Iterable, Literal

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

logger = logging.getLogger(__name__)


AdjustmentMode = Literal["none", "back_adjusted", "ratio"]


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FuturesCurveSnapshot:
    """One ``(symbol, expiry, snapshot_date)`` row.

    Mirrors :class:`aqp.persistence.models_macro.FuturesCurveRow` but in
    a plain dataclass shape so callers can pass it across Celery workers.
    """

    root_symbol: str
    expiry: dateType
    snapshot_date: dateType
    contract_symbol: str
    price: float
    volume: float | None = None
    open_interest: float | None = None
    provider: str | None = None


@dataclass(frozen=True, slots=True)
class StitchedCurveRow:
    """One row in the continuous, roll-adjusted curve."""

    snapshot_date: dateType
    price: float
    raw_price: float
    contract_symbol: str
    contract_expiry: dateType
    adjustment_factor: float  # additive for back_adjusted, multiplicative for ratio
    rolled: bool


@dataclass(slots=True)
class RollEvent:
    """Auditable record of a single roll transition."""

    snapshot_date: dateType
    from_contract: str
    from_expiry: dateType
    to_contract: str
    to_expiry: dateType
    rule_name: str
    from_price: float
    to_price: float


@dataclass
class FuturesCurve:
    """A continuous futures curve (root + contracts + snapshots).

    The curve is the unit of stitching: agents typically refer to "the
    ES curve" rather than to individual ES contracts. The curve carries
    all known contracts (ordered by expiry) and the snapshot rows for
    each, plus optional contract metadata.
    """

    root_symbol: str
    asset_class: str | None = None
    contract_size: float | None = None
    tick_size: float | None = None
    tick_value: float | None = None
    multiplier: float | None = None
    settlement_type: str | None = None
    snapshots: list[FuturesCurveSnapshot] = field(default_factory=list)
    contract_universe: list[str] = field(default_factory=list)
    underlying_index: str | None = None
    exchange: str | None = None


# ---------------------------------------------------------------------------
# Roll rules
# ---------------------------------------------------------------------------


class RollRule(ABC):
    """Abstract roll-rule strategy.

    Concrete subclasses implement :meth:`should_roll` answering "given
    the front-month snapshot and the next-month snapshot on this date,
    should we roll?". The stitcher walks day-by-day calling this hook.
    """

    name: str = "abstract"

    @abstractmethod
    def should_roll(
        self,
        *,
        front: FuturesCurveSnapshot,
        next_contract: FuturesCurveSnapshot,
        as_of: dateType,
    ) -> bool: ...


@dataclass(slots=True)
class VolumeBasedRoll(RollRule):
    """Roll when the next contract trades higher volume than the front.

    Mirrors what professional CTAs typically do: the contract with the
    deepest liquidity becomes the new front. Set ``min_volume_ratio``
    > 1.0 to require the next contract to trade *strictly* more than
    the front -- prevents jitter at the exact crossover point.
    """

    name: str = "volume"
    min_volume_ratio: float = 1.0

    def should_roll(
        self,
        *,
        front: FuturesCurveSnapshot,
        next_contract: FuturesCurveSnapshot,
        as_of: dateType,
    ) -> bool:
        if front.volume is None or next_contract.volume is None:
            return False
        if front.volume <= 0:
            return next_contract.volume > 0
        return (next_contract.volume / front.volume) > self.min_volume_ratio


@dataclass(slots=True)
class DateBasedRoll(RollRule):
    """Roll when within ``days_before_expiry`` calendar days of front expiry.

    Simplest rule, useful when no liquidity data is available. Defaults
    to 5 days -- typical for equity-index futures (ES, NQ) where
    settlement happens the Friday before expiry.
    """

    name: str = "date"
    days_before_expiry: int = 5

    def should_roll(
        self,
        *,
        front: FuturesCurveSnapshot,
        next_contract: FuturesCurveSnapshot,
        as_of: dateType,
    ) -> bool:
        delta = (front.expiry - as_of).days
        return delta <= self.days_before_expiry


@dataclass(slots=True)
class OpenInterestRoll(RollRule):
    """Roll when the next contract's open interest exceeds the front's.

    Complements :class:`VolumeBasedRoll` for instruments where volume is
    noisy but open interest is a stable indicator of position rotation.
    """

    name: str = "open_interest"
    min_oi_ratio: float = 1.0

    def should_roll(
        self,
        *,
        front: FuturesCurveSnapshot,
        next_contract: FuturesCurveSnapshot,
        as_of: dateType,
    ) -> bool:
        if front.open_interest is None or next_contract.open_interest is None:
            return False
        if front.open_interest <= 0:
            return (next_contract.open_interest or 0) > 0
        return (next_contract.open_interest / front.open_interest) > self.min_oi_ratio


# ---------------------------------------------------------------------------
# Stitching algorithm
# ---------------------------------------------------------------------------


def stitch_curve(
    curve: FuturesCurve,
    *,
    rule: RollRule | None = None,
    adjustment: AdjustmentMode = "back_adjusted",
) -> tuple[list[StitchedCurveRow], list[RollEvent]]:
    """Build the stitched continuous series + audit log of rolls.

    Returns a tuple ``(rows, rolls)``. ``rows`` is the per-day stitched
    series; ``rolls`` is the auditable list of every roll transition
    (date, from contract, to contract, prices), for downstream
    forensics.

    The algorithm:

    1. Group snapshots by ``snapshot_date``.
    2. For each date, identify the front contract (the unexpired
       contract with the earliest expiry) and the next contract.
    3. If the next contract exists and the roll rule says "roll", emit
       a :class:`RollEvent` and switch.
    4. Apply the adjustment factor (accumulated across rolls) to past
       prices.

    No backfilling -- dates missing from snapshots aren't synthesised.
    """
    rule = rule or VolumeBasedRoll()
    by_date: dict[dateType, list[FuturesCurveSnapshot]] = {}
    for s in curve.snapshots:
        by_date.setdefault(s.snapshot_date, []).append(s)

    if not by_date:
        return [], []

    dates_sorted = sorted(by_date.keys())
    rows: list[StitchedCurveRow] = []
    rolls: list[RollEvent] = []

    current_contract: str | None = None
    additive_offset = 0.0  # back-adjustment offset accumulator
    multiplicative_factor = 1.0  # ratio adjustment accumulator

    def _select_front(snaps: list[FuturesCurveSnapshot], today: dateType) -> FuturesCurveSnapshot | None:
        live = [s for s in snaps if s.expiry > today]
        if not live:
            return None
        live.sort(key=lambda s: s.expiry)
        return live[0]

    def _select_next(
        snaps: list[FuturesCurveSnapshot], front_expiry: dateType
    ) -> FuturesCurveSnapshot | None:
        successors = [s for s in snaps if s.expiry > front_expiry]
        if not successors:
            return None
        successors.sort(key=lambda s: s.expiry)
        return successors[0]

    for d in dates_sorted:
        snaps = by_date[d]
        front = _select_front(snaps, d)
        if front is None:
            # All contracts on this date already expired; skip.
            continue
        if current_contract is None:
            current_contract = front.contract_symbol

        next_snap = _select_next(snaps, front.expiry)
        rolled_today = False
        if next_snap is not None and front.contract_symbol == current_contract:
            if rule.should_roll(front=front, next_contract=next_snap, as_of=d):
                # Roll: switch to next contract; accumulate adjustment.
                if adjustment == "back_adjusted":
                    additive_offset += next_snap.price - front.price
                elif adjustment == "ratio":
                    if front.price != 0:
                        multiplicative_factor *= next_snap.price / front.price
                rolls.append(
                    RollEvent(
                        snapshot_date=d,
                        from_contract=current_contract,
                        from_expiry=front.expiry,
                        to_contract=next_snap.contract_symbol,
                        to_expiry=next_snap.expiry,
                        rule_name=rule.name,
                        from_price=front.price,
                        to_price=next_snap.price,
                    )
                )
                current_contract = next_snap.contract_symbol
                rolled_today = True

        # Emit the row using the current (possibly just-rolled) contract.
        active = (
            next_snap
            if rolled_today and next_snap is not None
            else front
            if front.contract_symbol == current_contract
            else next(
                (s for s in snaps if s.contract_symbol == current_contract), front
            )
        )
        adj_factor: float
        if adjustment == "back_adjusted":
            stitched_price = active.price + additive_offset
            adj_factor = additive_offset
        elif adjustment == "ratio":
            stitched_price = active.price * multiplicative_factor
            adj_factor = multiplicative_factor
        else:
            stitched_price = active.price
            adj_factor = 0.0

        rows.append(
            StitchedCurveRow(
                snapshot_date=d,
                price=float(stitched_price),
                raw_price=float(active.price),
                contract_symbol=active.contract_symbol,
                contract_expiry=active.expiry,
                adjustment_factor=float(adj_factor),
                rolled=rolled_today,
            )
        )

    return rows, rolls


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def list_curves() -> list[dict[str, Any]]:
    """List every distinct curve known to the platform.

    A curve is identified by its ``root_symbol`` (e.g. ``ES``, ``NQ``,
    ``CL``) and the rows in ``futures_curves`` aggregate per
    contract/day. Returns coarse metadata for the catalog UI / MCP tool.
    """
    from aqp.persistence.db import get_session
    from aqp.persistence.models_macro import FuturesCurveRow

    from sqlalchemy import func, select

    with get_session() as session:
        stmt = (
            select(
                FuturesCurveRow.root_symbol,
                func.count(FuturesCurveRow.id).label("snapshot_count"),
                func.min(FuturesCurveRow.snapshot_date).label("earliest"),
                func.max(FuturesCurveRow.snapshot_date).label("latest"),
                func.min(FuturesCurveRow.expiry).label("front_expiry"),
                func.max(FuturesCurveRow.expiry).label("back_expiry"),
            )
            .group_by(FuturesCurveRow.root_symbol)
            .order_by(FuturesCurveRow.root_symbol.asc())
        )
        rows = session.execute(stmt).all()
    return [
        {
            "root_symbol": r.root_symbol,
            "snapshot_count": int(r.snapshot_count),
            "earliest_date": r.earliest.isoformat() if r.earliest else None,
            "latest_date": r.latest.isoformat() if r.latest else None,
            "front_expiry": r.front_expiry.isoformat() if r.front_expiry else None,
            "back_expiry": r.back_expiry.isoformat() if r.back_expiry else None,
        }
        for r in rows
    ]


def load_curve_snapshots(
    root_symbol: str,
    *,
    start_date: dateType | None = None,
    end_date: dateType | None = None,
) -> FuturesCurve:
    """Load all snapshots for ``root_symbol`` and bundle them into a :class:`FuturesCurve`."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_macro import FuturesCurveRow

    from sqlalchemy import select

    with get_session() as session:
        stmt = select(FuturesCurveRow).where(FuturesCurveRow.root_symbol == root_symbol)
        if start_date is not None:
            stmt = stmt.where(FuturesCurveRow.snapshot_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(FuturesCurveRow.snapshot_date <= end_date)
        rows = session.execute(stmt).scalars().all()

    snapshots: list[FuturesCurveSnapshot] = []
    contracts_seen: set[str] = set()
    for r in rows:
        # The persistence row doesn't carry the per-contract symbol
        # explicitly -- we synthesise it from root + expiry month code.
        contract_symbol = _synthesize_contract_symbol(r.root_symbol, r.expiry)
        contracts_seen.add(contract_symbol)
        snapshots.append(
            FuturesCurveSnapshot(
                root_symbol=r.root_symbol,
                expiry=r.expiry,
                snapshot_date=r.snapshot_date,
                contract_symbol=contract_symbol,
                price=float(r.price),
                volume=None if r.volume is None else float(r.volume),
                open_interest=None
                if r.open_interest is None
                else float(r.open_interest),
                provider=r.provider,
            )
        )
    return FuturesCurve(
        root_symbol=root_symbol,
        snapshots=snapshots,
        contract_universe=sorted(contracts_seen),
    )


def stitched_to_arrow(
    rows: Iterable[StitchedCurveRow],
    *,
    root_symbol: str,
    rule_name: str,
    adjustment: AdjustmentMode,
) -> "pa.Table":
    """Convert stitched rows to a pyarrow ``Table`` for Iceberg writes.

    The output schema lines up with the
    ``aqp_gold_futures.continuous_curves`` table expected by the
    medallion-validated Iceberg helper. Callers wire the helper into
    ``iceberg_catalog.append_arrow`` with::

        from aqp.data.iceberg_catalog import append_arrow
        from aqp.data.catalog.active_metadata import BusinessMetadata

        append_arrow(
            "aqp_gold_futures.continuous_curves",
            stitched_to_arrow(rows, root_symbol="ES", rule_name="volume", adjustment="back_adjusted"),
            medallion_layer="gold",
            business_metadata=BusinessMetadata(
                data_owner="quant_research",
                semantic_definition="Continuous, roll-adjusted futures series.",
                reliability_score=0.95,
                domain="market.futures",
            ),
        )
    """
    import pyarrow as pa

    row_list = list(rows)
    cols = {
        "root_symbol": [root_symbol] * len(row_list),
        "snapshot_date": [r.snapshot_date for r in row_list],
        "price": [r.price for r in row_list],
        "raw_price": [r.raw_price for r in row_list],
        "contract_symbol": [r.contract_symbol for r in row_list],
        "contract_expiry": [r.contract_expiry for r in row_list],
        "adjustment_factor": [r.adjustment_factor for r in row_list],
        "rolled": [r.rolled for r in row_list],
        "rule_name": [rule_name] * len(row_list),
        "adjustment_mode": [str(adjustment)] * len(row_list),
        "stitched_at": [datetime.utcnow()] * len(row_list),
    }
    schema = pa.schema(
        [
            pa.field("root_symbol", pa.string()),
            pa.field("snapshot_date", pa.date32()),
            pa.field("price", pa.float64()),
            pa.field("raw_price", pa.float64()),
            pa.field("contract_symbol", pa.string()),
            pa.field("contract_expiry", pa.date32()),
            pa.field("adjustment_factor", pa.float64()),
            pa.field("rolled", pa.bool_()),
            pa.field("rule_name", pa.string()),
            pa.field("adjustment_mode", pa.string()),
            pa.field("stitched_at", pa.timestamp("us")),
        ]
    )
    arrays = [pa.array(cols[fld.name]) for fld in schema]
    return pa.Table.from_arrays(arrays, schema=schema)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


_MONTH_CODES = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]


def _synthesize_contract_symbol(root: str, expiry: dateType) -> str:
    """Build a CME-style contract symbol from ``(root, expiry)``.

    Format: ``{root}{month_code}{year_last_two}`` -- so the March 2026 ES
    contract becomes ``ESH26``. The mapping mirrors the CME's industry-
    standard month codes (F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun,
    N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec).
    """
    code = _MONTH_CODES[(expiry.month - 1) % 12]
    return f"{root}{code}{expiry.year % 100:02d}"


__all__ = [
    "AdjustmentMode",
    "DateBasedRoll",
    "FuturesCurve",
    "FuturesCurveSnapshot",
    "OpenInterestRoll",
    "RollEvent",
    "RollRule",
    "StitchedCurveRow",
    "VolumeBasedRoll",
    "list_curves",
    "load_curve_snapshots",
    "stitch_curve",
    "stitched_to_arrow",
]
