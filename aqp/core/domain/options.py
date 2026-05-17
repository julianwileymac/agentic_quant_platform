"""Options chain primitives.

Complements :mod:`aqp.core.domain.greeks` and
:class:`aqp.core.domain.instrument.OptionContract` with the descriptors used
to publish and query live option chains.

Phase 1 (migration 0039) adds :class:`OptionChainPayload` -- the Pydantic
wire model used to serialize an option chain over MCP and REST. The
columnar serializer addresses the OpenBB-flagged failure mode where
columnar ``{"strikes": [...], "expiries": [...], "bid": [...]}`` payloads
silently lose rows or balloon in memory when naively expanded into one dict
per record (see https://github.com/OpenBB-finance/OpenBB/issues/7473).

The payload class supports either columnar input (small wire payload, easy
for the LLM to inspect) or record input (one dict per slice), and emits a
canonical record list. A :meth:`OptionChainPayload.to_arrow` helper produces
the columnar Arrow ``RecordBatch`` callers need when persisting the chain
through :func:`aqp.data.iceberg_catalog.append_arrow`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as dateType, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterable

from pydantic import BaseModel, Field, model_serializer, model_validator

from aqp.core.domain.greeks import OptionGreekValues
from aqp.core.domain.identifiers import InstrumentId
from aqp.core.domain.instrument import OptionContract

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@dataclass(frozen=True)
class OptionSeriesId:
    """Identifier for a chain series ``(underlying, expiry)``.

    Implementations typically mint a stable string from
    ``{underlying}-{expiry.isoformat()}`` so resolvers can address "the 2026-06
    AAPL series" without listing every strike individually.
    """

    underlying: str
    expiry: dateType

    @property
    def value(self) -> str:
        return f"{self.underlying}-{self.expiry.isoformat()}"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class StrikeRange:
    """Inclusive strike range used when slicing a chain."""

    low: Decimal
    high: Decimal

    def contains(self, strike: Decimal) -> bool:
        return self.low <= strike <= self.high


@dataclass
class OptionChainSlice:
    """One strike per one expiry quote plus greeks snapshot."""

    instrument_id: InstrumentId
    series: OptionSeriesId
    strike: Decimal
    expiry: dateType
    kind: str  # "call" | "put"
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    volume: Decimal | None = None
    open_interest: Decimal | None = None
    implied_volatility: Decimal | None = None
    greeks: OptionGreekValues | None = None
    ts_event: datetime = field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2


@dataclass
class OptionChain:
    """Full chain (every strike per every kind) for an underlying plus expiry."""

    underlying: str
    expiry: dateType
    contracts: list[OptionContract] = field(default_factory=list)
    slices: list[OptionChainSlice] = field(default_factory=list)
    underlying_price: Decimal | None = None
    ts_event: datetime = field(default_factory=datetime.utcnow)

    @property
    def strikes(self) -> list[Decimal]:
        return sorted({s.strike for s in self.slices})

    @property
    def calls(self) -> list[OptionChainSlice]:
        return [s for s in self.slices if s.kind.lower() == "call"]

    @property
    def puts(self) -> list[OptionChainSlice]:
        return [s for s in self.slices if s.kind.lower() == "put"]

    def slice_at(self, strike: Decimal, kind: str) -> OptionChainSlice | None:
        wanted = kind.lower()
        for s in self.slices:
            if s.strike == strike and s.kind.lower() == wanted:
                return s
        return None


# ---------------------------------------------------------------------------
# Phase 1: Pydantic wire model plus columnar serializer
# ---------------------------------------------------------------------------


# The canonical record fields. Persisted columns (Arrow plus Iceberg) read
# from this list; any new column added here lands in every downstream emit.
OPTION_CHAIN_RECORD_FIELDS: tuple[str, ...] = (
    "strike",
    "expiry",
    "kind",
    "bid",
    "ask",
    "last",
    "mid",
    "mark",
    "volume",
    "open_interest",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "rho",
    "underlying_price",
    "ts_event",
)


class OptionChainRecord(BaseModel):
    """One option-chain row in record form.

    Records are emitted as ``list[OptionChainRecord]`` regardless of whether
    the upstream wire shape was columnar or record-form -- the
    :class:`OptionChainPayload` does the zipping once at the boundary.
    """

    strike: float
    expiry: dateType
    kind: str  # "call" | "put"
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    mid: float | None = None
    mark: float | None = None
    volume: float | None = None
    open_interest: float | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    underlying_price: float | None = None
    ts_event: datetime | None = None


class OptionChainPayload(BaseModel):
    """Wire-shape Pydantic model with columnar plus record dual ingestion.

    Accepted input shapes:

    1. **Columnar** (compact, OpenBB-style): each field is a list of
       equal length::

           {"strikes": [...], "expiries": [...], "bid": [...], ...}

       The validator zips them into records. Lists missing for optional
       fields are auto-filled with ``None``.

    2. **Record** (one dict per slice)::

           [{"strike": ..., "expiry": ..., "bid": ..., "kind": "call"}, ...]

       Passes through unchanged.

    The serializer always emits record form so downstream consumers don't
    need to know which shape was uploaded.
    """

    underlying: str
    expiry: dateType | None = None
    underlying_price: float | None = None
    ts_event: datetime = Field(default_factory=datetime.utcnow)
    records: list[OptionChainRecord] = Field(default_factory=list)
    provider: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_columnar(cls, data: Any) -> Any:
        """Zip columnar input into records before field validation runs.

        Accepts:

        - dict with both ``records`` and the columnar arrays -- records win
        - dict with columnar arrays only (``strikes`` / ``bid`` / ``ask`` /
          ``expiries`` / ``kinds`` ...) -- zipped into ``records``
        - dict with records already (passes through)
        """
        if not isinstance(data, dict):
            return data
        if data.get("records"):
            return data

        # Columnar key aliases (singular and plural variants).
        column_aliases: dict[str, tuple[str, ...]] = {
            "strike": ("strike", "strikes"),
            "expiry": ("expiry", "expiries", "expiration", "expirations"),
            "kind": ("kind", "kinds", "type", "types", "option_type"),
            "bid": ("bid", "bids", "bid_price"),
            "ask": ("ask", "asks", "ask_price"),
            "last": ("last", "last_price", "close"),
            "mid": ("mid", "mid_price"),
            "mark": ("mark", "mark_price"),
            "volume": ("volume", "volumes"),
            "open_interest": ("open_interest", "oi"),
            "implied_volatility": ("implied_volatility", "iv"),
            "delta": ("delta", "deltas"),
            "gamma": ("gamma", "gammas"),
            "theta": ("theta", "thetas"),
            "vega": ("vega", "vegas"),
            "rho": ("rho", "rhos"),
            "underlying_price": ("underlying_price", "spot", "underlying"),
            "ts_event": ("ts_event", "timestamp", "ts"),
        }

        # Find any columnar key.
        resolved: dict[str, list[Any]] = {}
        for canonical, aliases in column_aliases.items():
            for alias in aliases:
                if alias in data and isinstance(data[alias], (list, tuple)):
                    resolved[canonical] = list(data[alias])
                    break

        if not resolved:
            return data

        # Length check -- every present column must agree. We pick the
        # longest one and pad shorter ones with ``None`` so malformed
        # payloads still produce a record set rather than silently
        # dropping rows the report flags.
        max_len = max(len(v) for v in resolved.values())
        records: list[dict[str, Any]] = []
        for i in range(max_len):
            rec: dict[str, Any] = {}
            for canonical, column in resolved.items():
                rec[canonical] = column[i] if i < len(column) else None
            # Mandatory fields default if missing.
            if "kind" not in rec or rec["kind"] is None:
                rec["kind"] = "call"
            if "strike" not in rec or rec["strike"] is None:
                continue  # skip rows with no strike -- they're meaningless
            if "expiry" not in rec or rec["expiry"] is None:
                rec["expiry"] = data.get("expiry")
                if rec["expiry"] is None:
                    continue
            records.append(rec)

        out = dict(data)
        out["records"] = records
        # Strip the now-zipped columnar keys so the model doesn't see them
        # twice.
        for alias_list in column_aliases.values():
            for alias in alias_list:
                out.pop(alias, None)
        return out

    @model_serializer(mode="wrap")
    def _emit_records(self, handler: Any) -> dict[str, Any]:
        """Always emit record form on serialize.

        ``handler`` is the default Pydantic v2 serializer chain. We let it
        run, then assert the records are present so downstream callers
        don't accidentally consume the columnar shape we accept on input.
        """
        out = handler(self)
        # If for some reason ``records`` was emitted as a Pydantic model
        # rather than a dict (some serializer modes), re-coerce.
        if isinstance(out, dict):
            recs = out.get("records") or []
            out["records"] = [
                r.model_dump() if hasattr(r, "model_dump") else r for r in recs
            ]
        return out

    def iter_records(self) -> Iterable[OptionChainRecord]:
        """Iterate the canonical record list."""
        return iter(self.records)

    def to_arrow(self) -> "pa.RecordBatch":
        """Emit a columnar Arrow ``RecordBatch`` for Iceberg writes.

        ``aqp.data.iceberg_catalog.append_arrow`` accepts ``RecordBatch``
        directly; this is the bridge from the OpenBB-style columnar
        wire shape to the medallion-validated write path. Decimals
        round-trip as ``pa.float64``.
        """
        import pyarrow as pa

        cols: dict[str, list[Any]] = {name: [] for name in OPTION_CHAIN_RECORD_FIELDS}
        for r in self.records:
            cols["strike"].append(float(r.strike))
            cols["expiry"].append(r.expiry)
            cols["kind"].append(str(r.kind))
            cols["bid"].append(None if r.bid is None else float(r.bid))
            cols["ask"].append(None if r.ask is None else float(r.ask))
            cols["last"].append(None if r.last is None else float(r.last))
            cols["mid"].append(None if r.mid is None else float(r.mid))
            cols["mark"].append(None if r.mark is None else float(r.mark))
            cols["volume"].append(None if r.volume is None else float(r.volume))
            cols["open_interest"].append(
                None if r.open_interest is None else float(r.open_interest)
            )
            cols["implied_volatility"].append(
                None if r.implied_volatility is None else float(r.implied_volatility)
            )
            cols["delta"].append(None if r.delta is None else float(r.delta))
            cols["gamma"].append(None if r.gamma is None else float(r.gamma))
            cols["theta"].append(None if r.theta is None else float(r.theta))
            cols["vega"].append(None if r.vega is None else float(r.vega))
            cols["rho"].append(None if r.rho is None else float(r.rho))
            cols["underlying_price"].append(
                None
                if r.underlying_price is None
                else float(r.underlying_price)
            )
            cols["ts_event"].append(r.ts_event or self.ts_event)

        schema = pa.schema(
            [
                pa.field("strike", pa.float64()),
                pa.field("expiry", pa.date32()),
                pa.field("kind", pa.string()),
                pa.field("bid", pa.float64()),
                pa.field("ask", pa.float64()),
                pa.field("last", pa.float64()),
                pa.field("mid", pa.float64()),
                pa.field("mark", pa.float64()),
                pa.field("volume", pa.float64()),
                pa.field("open_interest", pa.float64()),
                pa.field("implied_volatility", pa.float64()),
                pa.field("delta", pa.float64()),
                pa.field("gamma", pa.float64()),
                pa.field("theta", pa.float64()),
                pa.field("vega", pa.float64()),
                pa.field("rho", pa.float64()),
                pa.field("underlying_price", pa.float64()),
                pa.field("ts_event", pa.timestamp("us")),
            ]
        )
        arrays = [pa.array(cols[fld.name]) for fld in schema]
        return pa.RecordBatch.from_arrays(arrays, schema=schema)

    def to_option_chain(self) -> OptionChain:
        """Lift records back into the legacy :class:`OptionChain` dataclass.

        Bridges the Pydantic wire shape to the existing in-memory chain
        used by Greeks / Greeks-cache code paths. Greeks present on the
        record are attached so consumers don't lose them.
        """
        slices: list[OptionChainSlice] = []
        from aqp.core.domain.identifiers import (
            InstrumentId as InstId,
            Symbol2,
            Venue,
        )

        # Reuse a single InstrumentId placeholder per (kind, strike) so
        # the chain dataclass stays cheap; the resolver service refines
        # this if the chain is later loaded by series id.
        venue = Venue("MULTI")
        for r in self.records:
            sym = Symbol2(f"{self.underlying}-{r.expiry.isoformat()}-{r.kind}-{r.strike}")
            iid = InstId(sym, venue)
            series = OptionSeriesId(underlying=self.underlying, expiry=r.expiry)
            greeks = None
            if any(
                g is not None
                for g in (r.delta, r.gamma, r.theta, r.vega, r.rho)
            ):
                greeks = OptionGreekValues(
                    delta=None if r.delta is None else Decimal(str(r.delta)),
                    gamma=None if r.gamma is None else Decimal(str(r.gamma)),
                    theta=None if r.theta is None else Decimal(str(r.theta)),
                    vega=None if r.vega is None else Decimal(str(r.vega)),
                    rho=None if r.rho is None else Decimal(str(r.rho)),
                )
            slices.append(
                OptionChainSlice(
                    instrument_id=iid,
                    series=series,
                    strike=Decimal(str(r.strike)),
                    expiry=r.expiry,
                    kind=r.kind,
                    bid=None if r.bid is None else Decimal(str(r.bid)),
                    ask=None if r.ask is None else Decimal(str(r.ask)),
                    last=None if r.last is None else Decimal(str(r.last)),
                    volume=None if r.volume is None else Decimal(str(r.volume)),
                    open_interest=(
                        None
                        if r.open_interest is None
                        else Decimal(str(r.open_interest))
                    ),
                    implied_volatility=(
                        None
                        if r.implied_volatility is None
                        else Decimal(str(r.implied_volatility))
                    ),
                    greeks=greeks,
                    ts_event=r.ts_event or self.ts_event,
                )
            )
        return OptionChain(
            underlying=self.underlying,
            expiry=self.expiry or (slices[0].expiry if slices else None),  # type: ignore[arg-type]
            contracts=[],
            slices=slices,
            underlying_price=(
                None
                if self.underlying_price is None
                else Decimal(str(self.underlying_price))
            ),
            ts_event=self.ts_event,
        )


__all__ = [
    "OPTION_CHAIN_RECORD_FIELDS",
    "OptionChain",
    "OptionChainPayload",
    "OptionChainRecord",
    "OptionChainSlice",
    "OptionSeriesId",
    "StrikeRange",
]
