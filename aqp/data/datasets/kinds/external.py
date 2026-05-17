"""``ExternalDataset`` — sentinel for uningested catalog entries.

Phase 1 introduces "discoverable but not materialised" entries; the
metadata cache lists them so quantitative researchers can find them,
and the Airbyte builder can promote them. ``_load`` raises
:class:`DatasetNotMaterialized` so any caller that tries to read the
payload gets a clean signal to invoke the promote endpoint.
"""
from __future__ import annotations

from typing import Any

from aqp.data.datasets.base import BaseDataset
from aqp.data.datasets.exceptions import DatasetNotMaterialized, DatasetSaveDisabled


class ExternalDataset(BaseDataset):
    kind = "external"
    writable = False

    def _validate_spec(self) -> None:
        cfg = self._spec.config
        if not str(cfg.get("source_uri") or cfg.get("docs_url") or "").strip():
            raise ValueError(
                "ExternalDataset requires at least one of config.source_uri or config.docs_url"
            )

    def _load(self) -> Any:
        raise DatasetNotMaterialized(
            "ExternalDataset has not been ingested yet; promote it via the discovery browser "
            "to attach a real connector kind."
        )

    def _save(self, payload: Any) -> Any:
        raise DatasetSaveDisabled("ExternalDataset is read-only")

    def _exists(self) -> bool:
        return False

    def _describe(self) -> dict[str, Any]:
        cfg = self._spec.config
        return {
            "source_uri": cfg.get("source_uri"),
            "docs_url": cfg.get("docs_url"),
            "intent_kind": cfg.get("intent_kind"),
            "load_mode": "external",
        }


__all__ = ["ExternalDataset"]
