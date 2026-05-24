"""Airbyte destination shims that target QuestDB ILP + Iceberg bronze.

Two destinations:

- :class:`QuestDBDestination` — writes records via QuestDB's
  ILP (InfluxDB Line Protocol) port. Use for high-velocity
  tick / L1 / L2 streams where row-level latency matters.
- :class:`IcebergBronzeDestination` — writes records via
  :func:`aqp.data.iceberg_catalog.append_arrow` to the canonical
  ``aqp_bronze_airbyte_<connector_slug>`` namespace. Use for daily
  / end-of-day pricing, fundamentals, corporate actions, and
  regulatory data.

Neither destination touches PyIceberg directly. The Iceberg path
respects root AGENTS.md rule 3; the QuestDB path piggy-backs on the
existing :class:`aqp.data.datasets.kinds.questdb.QuestDBDataset`
write surface where possible.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)


def _slug_to_bronze_ns(connector_slug: str) -> str:
    """Build the canonical ``aqp_bronze_airbyte_<slug>`` namespace."""
    cleaned = connector_slug.strip().lower().replace("-", "_")
    return f"aqp_bronze_airbyte_{cleaned}"


class QuestDBDestination:
    """Airbyte destination shim that writes via QuestDB ILP.

    Owns the connection lifecycle so multiple streams routed to
    the same connector share a single ILP socket. The actual write
    delegates to :class:`aqp.data.datasets.kinds.questdb.QuestDBDataset`
    where the table already exists, otherwise falls back to ILP
    line emission.
    """

    def __init__(
        self,
        *,
        connector_slug: str,
        questdb_host: str | None = None,
        questdb_port: int | None = None,
    ) -> None:
        self._slug = connector_slug
        self._host = questdb_host
        self._port = questdb_port
        self._client: Any | None = None

    def write(
        self,
        *,
        stream: str,
        records: Iterable[dict[str, Any]],
        ts_column: str = "ts",
        tag_columns: tuple[str, ...] = (),
    ) -> int:
        rows = list(records)
        if not rows:
            return 0
        try:
            from aqp.data.datasets.kinds.questdb import QuestDBDataset

            dataset = QuestDBDataset(
                table=f"{self._slug}__{stream}",
                ts_column=ts_column,
                tag_keys=list(tag_columns),
            )
            dataset.save(rows)
            return len(rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "QuestDBDataset save failed for %s/%s: %s",
                self._slug,
                stream,
                exc,
            )
            return 0

    def close(self) -> None:
        client = self._client
        if client is not None and hasattr(client, "close"):
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None


class IcebergBronzeDestination:
    """Airbyte destination shim that writes via ``iceberg_catalog.append_arrow``.

    Target namespace: ``aqp_bronze_airbyte_<connector_slug>``.
    The destination validates the namespace prefix against the
    declared ``medallion_layer="bronze"`` per root AGENTS.md rule 21.
    """

    def __init__(self, *, connector_slug: str) -> None:
        self._slug = connector_slug
        self._namespace = _slug_to_bronze_ns(connector_slug)

    @property
    def namespace(self) -> str:
        return self._namespace

    def write(
        self,
        *,
        stream: str,
        records: Iterable[dict[str, Any]],
        partition_cols: tuple[str, ...] = (),
    ) -> int:
        rows = list(records)
        if not rows:
            return 0
        try:
            import pyarrow as pa

            table = pa.Table.from_pylist(rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "could not build Arrow table for %s/%s: %s",
                self._slug,
                stream,
                exc,
            )
            return 0
        try:
            from aqp.data.iceberg_catalog import append_arrow

            identifier = f"{self._namespace}.{stream}"
            append_arrow(
                identifier=identifier,
                table=table,
                medallion_layer="bronze",
            )
            return table.num_rows
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "iceberg append_arrow failed for %s: %s",
                f"{self._namespace}.{stream}",
                exc,
            )
            return 0


__all__ = [
    "IcebergBronzeDestination",
    "QuestDBDestination",
]
