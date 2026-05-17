"""FRED Observations fetcher.

Wraps :class:`aqp.data.sources.fred.series.FredSeriesAdapter` so the
existing adapter keeps owning the FRED-specific schema, identifier
normalization, and lineage emission while the new Fetcher contract
bridges it into the unified engine.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fabric.schema_registry import MacroIndicatorSchema
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    RateLimit,
    register_source_fetcher,
)
from aqp.data.fetchers.fabric_mixin import FabricFetcherMixin

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.fred",
    display_name="FRED (Federal Reserve Economic Data)",
    kind=FetcherKind.API,
    description="Fetch a FRED series and stream its observations.",
    base_url="https://api.stlouisfed.org/fred",
    auth_type="api_key",
    credentials_ref="AQP_FRED_API_KEY",
    rate_limit=RateLimit(requests_per_minute=120),
    capabilities=(
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
        FetcherCapability.REQUIRES_AUTH.value,
    ),
    domains=("economic.series",),
)
class FredObservationsFetcher(Fetcher, FabricFetcherMixin):
    """Stream FRED observations as Arrow batches."""

    CANONICAL_SCHEMA_CLASS = MacroIndicatorSchema
    SUPPORTED_INTERVALS = ("daily", "weekly", "monthly", "quarterly", "annual")
    REQUIRES_AUTH = False
    PROVIDER_NAME = "FRED"
    MEDALLION_LAYER = "bronze"
    capabilities = (
        FetcherCapability.SUPPORTS_INCREMENTAL,
        FetcherCapability.REQUIRES_AUTH,
    )
    default_rate_limit = RateLimit(requests_per_minute=120)

    def __init__(
        self,
        *,
        series_id: str,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        units: str | None = None,
        frequency: str | None = None,
        persist: bool = False,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        if not series_id:
            raise ValueError("FredObservationsFetcher: series_id required")
        self.series_id = series_id
        self.start = start
        self.end = end
        self.units = units
        self.frequency = frequency
        self.persist = persist
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"fred://{self.series_id}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        from aqp.data.sources.fred.series import FredSeriesAdapter

        ctx.emit("source", f"fred series_id={self.series_id}")
        adapter = FredSeriesAdapter()
        result = adapter.fetch_observations(
            series_id=self.series_id,
            start=self.start,
            end=self.end,
            units=self.units,
            frequency=self.frequency,
            persist=self.persist,
            emit_lineage=False,
        )
        df = getattr(result, "data", None)
        if df is None or len(df) == 0:
            return
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)

    def normalize_schema(self, raw: Any) -> pa.Table:
        """Map FRED response columns into :class:`MacroIndicatorSchema`."""
        import pandas as pd
        import pyarrow as pa

        if isinstance(raw, pa.Table):
            frame = raw.to_pandas()
        elif hasattr(raw, "to_pandas") and callable(getattr(raw, "to_pandas")):
            frame = raw.to_pandas()
        elif isinstance(raw, list):
            frame = pd.DataFrame(raw)
        else:
            frame = pd.DataFrame(raw)

        if frame.empty:
            frame = pd.DataFrame(columns=["series_id", "observation_date", "value"])

        frame = frame.rename(columns={"date": "observation_date"})
        if "series_id" not in frame.columns:
            frame["series_id"] = self.series_id
        frame["source"] = "FRED"
        frame["observation_date"] = pd.to_datetime(
            frame.get("observation_date"),
            utc=True,
            errors="coerce",
        )
        vintage_raw = frame.get("vintage_date")
        if vintage_raw is None:
            vintage_raw = frame.get("realtime_start")
        frame["vintage_date"] = pd.to_datetime(vintage_raw, utc=True, errors="coerce")
        frame["revision_number"] = pd.to_numeric(
            frame.get("revision_number", 0),
            errors="coerce",
        ).fillna(0).astype("int32")
        frame["value"] = pd.to_numeric(frame.get("value"), errors="coerce")
        normalized = frame[
            [
                "series_id",
                "source",
                "observation_date",
                "vintage_date",
                "revision_number",
                "value",
            ]
        ]
        return FabricFetcherMixin.normalize_schema(self, normalized)
