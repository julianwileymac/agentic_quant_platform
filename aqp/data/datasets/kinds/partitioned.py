"""Kedro ``PartitionedDataset`` analogue.

Lists files matching ``glob`` under ``base_path`` and exposes them as a
mapping of ``{partition_key: payload}``. Useful for parquet folders
laid out by hive-style date partitions, exporter outputs, or vendor
zip drops sitting in ``data/raw/<date>/...``.

Spec config schema::

    {
      "base_path": "s3://bucket/incoming/",     # required
      "glob": "*.parquet",                       # optional, default "*"
      "partition_key": "filename",               # 'filename' | 'parent' | 'relative'
      "child_kind": "parquet",                   # required, kind for individual children
      "child_config_overrides": {...},           # merged into each child config
      "storage_options": {...},                  # optional fsspec kwargs
    }
"""
from __future__ import annotations

import os
from typing import Any

from aqp.data.datasets.base import BaseDataset
from aqp.data.datasets.exceptions import DatasetSaveDisabled
from aqp.data.datasets.registry import get_dataset_kind
from aqp.data.datasets.spec import DatasetSpec


class PartitionedDataset(BaseDataset):
    kind = "partitioned"
    writable = False  # writes happen on the child kinds

    def _validate_spec(self) -> None:
        cfg = self._spec.config
        if not str(cfg.get("base_path") or "").strip():
            raise ValueError("PartitionedDataset requires config.base_path")
        if not str(cfg.get("child_kind") or "").strip():
            raise ValueError("PartitionedDataset requires config.child_kind")
        # Eagerly validate the child kind exists so config errors are
        # caught at spec time rather than when loading partitions.
        get_dataset_kind(str(cfg["child_kind"]))

    @property
    def base_path(self) -> str:
        return str(self._spec.config["base_path"]).rstrip("/")

    @property
    def glob_pattern(self) -> str:
        return str(self._spec.config.get("glob") or "*")

    def _list_partitions(self) -> list[tuple[str, str]]:
        cfg = self._spec.config
        try:
            import fsspec  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("fsspec is required for PartitionedDataset") from exc
        storage_options = dict(cfg.get("storage_options") or {})
        fs, root = fsspec.core.url_to_fs(self.base_path, **storage_options)
        glob_pattern = f"{root}/**/{self.glob_pattern}"
        # fsspec's glob with ** can be expensive — call it once.
        try:
            paths = fs.glob(glob_pattern)
        except Exception:  # noqa: BLE001
            paths = []
        out: list[tuple[str, str]] = []
        partition_key_kind = str(cfg.get("partition_key") or "relative").lower()
        for p in paths:
            full = str(p)
            if partition_key_kind == "filename":
                key = os.path.basename(full)
            elif partition_key_kind == "parent":
                key = os.path.basename(os.path.dirname(full))
            else:
                rel = full[len(root) :].lstrip("/") if full.startswith(root) else full
                key = rel
            # Reconstruct a valid URL the child kind can read. fsspec
            # returns the protocol-relative path; we keep the original
            # protocol from base_path.
            if "://" in self.base_path and "://" not in full:
                proto = self.base_path.split("://", 1)[0]
                full_url = f"{proto}://{full}"
            else:
                full_url = full
            out.append((key, full_url))
        return sorted(out)

    def _load(self) -> Any:
        cfg = self._spec.config
        child_kind = str(cfg["child_kind"])
        overrides = dict(cfg.get("child_config_overrides") or {})
        cls = get_dataset_kind(child_kind)
        out: dict[str, Any] = {}
        for key, full_path in self._list_partitions():
            child_cfg = {"filepath": full_path, **overrides}
            child_spec = DatasetSpec(
                kind=child_kind,
                config=child_cfg,
                medallion_layer=self.medallion_layer,
                business_metadata=self._spec.business_metadata,
                data_contract=self._spec.data_contract,
            )
            child = cls(child_spec)
            out[key] = child.load
        return out

    def _save(self, payload: Any) -> Any:
        raise DatasetSaveDisabled(
            "PartitionedDataset does not write directly; instantiate the child kind"
            " with the desired filepath and call save()"
        )

    def _exists(self) -> bool:
        return bool(self._list_partitions())

    def _describe(self) -> dict[str, Any]:
        return {
            "base_path": self.base_path,
            "glob": self.glob_pattern,
            "child_kind": self._spec.config["child_kind"],
            "load_mode": "partitioned",
        }


__all__ = ["PartitionedDataset"]
