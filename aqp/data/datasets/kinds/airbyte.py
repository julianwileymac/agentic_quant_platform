"""Airbyte-backed :class:`BaseDataset` kind (Phase 1, plan section 5).

Closes the rule-29 gap documented during exploration: Airbyte-synced
data has no typed `DatasetSpec` today; the `materialization_manifest`
on :class:`aqp.persistence.models_airbyte.AirbyteConnectionRow`
carries raw JSON instead of a hashable spec.

`AirbyteDataset` makes every Airbyte connection a typed catalog
entry. The spec carries the workspace, connection, stream
identifiers, the canonical
``aqp_bronze_airbyte_<connector_slug>`` Iceberg namespace, and the
rate-limit class so the metadata cache + Vite EntityPicker can
surface the connection like any other dataset.

`_load` is a thin proxy to the underlying bronze
:class:`IcebergDataset` — once Airbyte syncs into bronze, the
Iceberg-side read path is the same.
`_save` is intentionally rejected — Airbyte-synced data is
write-via-Airbyte only; the Iceberg destination handles the
actual append through
:func:`aqp.data.iceberg_catalog.append_arrow` (rule 3).
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.data.datasets.base import BaseDataset

logger = logging.getLogger(__name__)


_BRONZE_PREFIX = "aqp_bronze_airbyte_"


def airbyte_bronze_namespace(connector_slug: str) -> str:
    """Build the canonical bronze namespace for an Airbyte connector."""
    cleaned = connector_slug.strip().lower().replace("-", "_")
    return f"{_BRONZE_PREFIX}{cleaned}"


class AirbyteDataset(BaseDataset):
    """Typed dataset spec for an Airbyte connection + stream."""

    kind = "airbyte"
    writable = False  # writes go through Airbyte sync jobs

    def _validate_spec(self) -> None:
        cfg = self._spec.config
        for required in ("workspace_id", "connection_id", "stream", "connector_slug"):
            if not str(cfg.get(required, "") or "").strip():
                raise ValueError(
                    f"AirbyteDataset requires config.{required}"
                )
        slug = str(cfg.get("connector_slug", "")).strip().lower()
        bronze_ns = cfg.get("bronze_namespace") or airbyte_bronze_namespace(slug)
        if not str(bronze_ns).startswith(_BRONZE_PREFIX):
            raise ValueError(
                f"AirbyteDataset.bronze_namespace must start with {_BRONZE_PREFIX!r}; "
                f"got {bronze_ns!r}"
            )
        # Force the layer field so the catalog upsert + medallion guard
        # see the bronze designation without the operator having to set
        # it twice.
        if not self._spec.medallion_layer:
            self._spec.medallion_layer = "bronze"

    @property
    def connector_slug(self) -> str:
        return str(self._spec.config["connector_slug"]).strip().lower()

    @property
    def bronze_namespace(self) -> str:
        cfg = self._spec.config
        return str(
            cfg.get("bronze_namespace") or airbyte_bronze_namespace(self.connector_slug)
        )

    @property
    def stream(self) -> str:
        return str(self._spec.config["stream"])

    @property
    def iceberg_identifier(self) -> str:
        return f"{self.bronze_namespace}.{self.stream}"

    def _load(self) -> Any:
        from aqp.data import iceberg_catalog

        cfg = self._spec.config
        limit = cfg.get("limit") or cfg.get("head")
        columns = cfg.get("columns")
        return iceberg_catalog.read_arrow(
            self.iceberg_identifier,
            columns=columns,
            limit=limit,
        )

    def _save(self, payload: Any) -> Any:
        raise NotImplementedError(
            "AirbyteDataset is not directly writable. The Airbyte sync "
            "job + IcebergBronzeDestination handle writes through "
            "iceberg_catalog.append_arrow."
        )

    def _exists(self) -> bool:
        try:
            from aqp.data import iceberg_catalog

            return iceberg_catalog.table_exists(self.iceberg_identifier)
        except Exception:  # noqa: BLE001
            return False


__all__ = ["AirbyteDataset", "airbyte_bronze_namespace"]
