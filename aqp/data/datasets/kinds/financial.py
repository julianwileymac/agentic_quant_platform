"""Financial-data :class:`BaseDataset` kinds (Phase 2, plan section 6).

Four typed kinds for the canonical AQP financial datasets. Each
inherits the metaclass-driven registration from
:class:`BaseDataset` and routes reads / writes through the
appropriate underlying kind (QuestDB ILP for high-velocity,
Iceberg for canonical history).

- :class:`OHLCVBarsDataset` — minute / hour / day bars. Lives in
  QuestDB; ``aqp/data/dbt/projects/core/models/core_facts/`` is
  the canonical write path. The dataset surface is read-only +
  metadata-only; agents read via MCP, not via direct DB calls
  (rule 22).
- :class:`L2OrderBookDataset` — Level-2 order-book snapshots
  with float64 ARRAY columns per QuestDB 9.0+. Lives in
  QuestDB. Per-hour partitioning.
- :class:`CorporateActionsDataset` — splits / dividends / mergers
  SCD2 backing the ``snap_corporate_actions`` dbt snapshot. Read
  surface for backtest engines that need point-in-time
  reconstruction.
- :class:`IndexConstituentsDataset` — index membership SCD2 backing
  the ``snap_index_constituents`` dbt snapshot.

The spec config carries enough metadata that downstream agents
can introspect the cursor field, primary key, and partition
strategy without touching the underlying DB.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.data.datasets.base import BaseDataset

logger = logging.getLogger(__name__)


class _FinancialKindBase(BaseDataset):
    """Shared helpers for OHLCV / L2 / corporate-actions / index kinds."""

    timestamp_field: str = "ts"
    primary_key_fields: tuple[str, ...] = ()

    def _validate_spec(self) -> None:
        # Each subclass requires `table`; everything else is optional
        # with sensible defaults.
        table = str(self._spec.config.get("table") or "").strip()
        if not table:
            raise ValueError(f"{self.kind!r} dataset requires config.table")

    @property
    def table(self) -> str:
        return str(self._spec.config["table"])


class OHLCVBarsDataset(_FinancialKindBase):
    """Minute / hour / day OHLCV bars in QuestDB."""

    kind = "ohlcv_bars"
    writable = False  # writes flow through the dbt core_facts model
    timestamp_field = "ts"
    primary_key_fields = ("symbol", "ts")

    def _validate_spec(self) -> None:
        super()._validate_spec()
        granularity = str(self._spec.config.get("granularity", "minute"))
        if granularity not in {"minute", "5min", "15min", "hour", "day"}:
            raise ValueError(
                f"OHLCVBarsDataset.granularity must be one of "
                "{minute, 5min, 15min, hour, day}; got "
                f"{granularity!r}"
            )

    def _load(self) -> Any:
        from aqp.data.datasets.kinds.questdb import QuestDBDataset

        return QuestDBDataset(
            self._spec.model_copy(update={"kind": "questdb"})  # type: ignore[arg-type]
        )._load()

    def _save(self, payload: Any) -> Any:
        raise NotImplementedError(
            "OHLCVBarsDataset writes flow through the dbt core_facts "
            "models — call dbt build instead of writing directly."
        )


class L2OrderBookDataset(_FinancialKindBase):
    """Level-2 order-book snapshots using QuestDB float64 ARRAY columns."""

    kind = "l2_orderbook"
    writable = True  # ILP destination writes from streaming connectors
    timestamp_field = "ts"
    primary_key_fields = ("symbol", "ts")

    def _validate_spec(self) -> None:
        super()._validate_spec()
        depth = int(self._spec.config.get("depth", 10))
        if depth < 1 or depth > 100:
            raise ValueError(
                "L2OrderBookDataset.depth must be in [1, 100]; "
                f"got {depth}"
            )

    def _load(self) -> Any:
        from aqp.data.datasets.kinds.questdb import QuestDBDataset

        return QuestDBDataset(
            self._spec.model_copy(update={"kind": "questdb"})  # type: ignore[arg-type]
        )._load()

    def _save(self, payload: Any) -> Any:
        from aqp.data.datasets.kinds.questdb import QuestDBDataset

        return QuestDBDataset(
            self._spec.model_copy(update={"kind": "questdb"})  # type: ignore[arg-type]
        )._save(payload)


class CorporateActionsDataset(_FinancialKindBase):
    """SCD2 corporate actions backing the snap_corporate_actions snapshot."""

    kind = "corporate_actions"
    writable = False  # writes flow through dbt snapshot
    timestamp_field = "dbt_valid_from"
    primary_key_fields = ("action_id",)

    def _load(self) -> Any:
        from aqp.data.datasets.kinds.iceberg import IcebergDataset

        return IcebergDataset(
            self._spec.model_copy(update={"kind": "iceberg"})  # type: ignore[arg-type]
        )._load()

    def _save(self, payload: Any) -> Any:
        raise NotImplementedError(
            "CorporateActionsDataset writes flow through `dbt snapshot` — "
            "call the snap_corporate_actions snapshot."
        )


class IndexConstituentsDataset(_FinancialKindBase):
    """SCD2 index constituents backing the snap_index_constituents snapshot."""

    kind = "index_constituents"
    writable = False  # writes flow through dbt snapshot
    timestamp_field = "dbt_valid_from"
    primary_key_fields = ("index", "symbol")

    def _load(self) -> Any:
        from aqp.data.datasets.kinds.iceberg import IcebergDataset

        return IcebergDataset(
            self._spec.model_copy(update={"kind": "iceberg"})  # type: ignore[arg-type]
        )._load()

    def _save(self, payload: Any) -> Any:
        raise NotImplementedError(
            "IndexConstituentsDataset writes flow through `dbt snapshot` — "
            "call the snap_index_constituents snapshot."
        )


__all__ = [
    "CorporateActionsDataset",
    "IndexConstituentsDataset",
    "L2OrderBookDataset",
    "OHLCVBarsDataset",
]
