"""Iceberg-backed :class:`BaseDataset` (the canonical AQP kind).

``_save`` routes through :func:`aqp.data.iceberg_catalog.append_arrow`
so it inherits AGENTS hard rule 3 (single Iceberg write entry-point) +
rule 21 (medallion namespace validation). Never call PyIceberg
directly from this kind.

Spec config schema::

    {
      "identifier": "aqp_bronze_demo.bars",  # required
      "head": 1024,                           # optional read limit
      "limit": 1024,                          # alias for head
      "partition_filter": null,               # optional, future use
    }
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.data.datasets.base import BaseDataset

logger = logging.getLogger(__name__)


class IcebergDataset(BaseDataset):
    """Read / append an Iceberg table through the catalog wrapper."""

    kind = "iceberg"
    writable = True

    def _validate_spec(self) -> None:
        identifier = str(self._spec.config.get("identifier") or "").strip()
        if not identifier:
            raise ValueError("IcebergDataset requires config.identifier")
        if "." not in identifier:
            raise ValueError(
                "IcebergDataset.config.identifier must be 'namespace.table'"
            )
        # Validate medallion namespace -> layer alignment when both are
        # provided. The wrapper enforces this on append_arrow too; we
        # raise early to give the discovery / builder UIs a clean
        # validation signal.
        layer = self.medallion_layer
        if layer is not None:
            from aqp.data.catalog.active_metadata import validate_layer_for_namespace

            validate_layer_for_namespace(layer, identifier)

    @property
    def identifier(self) -> str:
        return str(self._spec.config["identifier"])

    def _load(self) -> Any:
        from aqp.data import iceberg_catalog

        cfg = self._spec.config
        limit = cfg.get("limit") or cfg.get("head")
        columns = cfg.get("columns")
        return iceberg_catalog.read_arrow(
            self.identifier,
            columns=columns,
            limit=limit,
        )

    def _save(self, payload: Any) -> Any:
        from aqp.data import iceberg_catalog

        return iceberg_catalog.append_arrow(
            self.identifier,
            payload,
            medallion_layer=self.medallion_layer,
            business_metadata=self._spec.business_metadata or None,
            data_contract=self._spec.data_contract or None,
        )

    def _exists(self) -> bool:
        from aqp.data import iceberg_catalog

        try:
            return iceberg_catalog.load_table(self.identifier) is not None
        except Exception:  # noqa: BLE001
            return False

    def _describe(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "load_mode": "iceberg",
        }


__all__ = ["IcebergDataset"]
