"""Parquet ``BaseDataset`` — read / write a parquet path via fsspec.

Spec config schema::

    {
      "filepath": "s3://bucket/key.parquet",  # required
      "storage_options": {...},                # optional fsspec kwargs
      "load_args": {...},                      # optional pyarrow.parquet.read_table kwargs
      "save_args": {...},                      # optional pyarrow.parquet.write_table kwargs
    }
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from aqp.data.datasets.base import BaseDataset


class ParquetDataset(BaseDataset):
    kind = "parquet"
    writable = True

    def _validate_spec(self) -> None:
        if not str(self._spec.config.get("filepath") or "").strip():
            raise ValueError("ParquetDataset requires config.filepath")

    @property
    def filepath(self) -> str:
        return str(self._spec.config["filepath"])

    def _open_fs(self):
        try:
            import fsspec  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("fsspec is required for ParquetDataset") from exc
        storage_options = dict(self._spec.config.get("storage_options") or {})
        return fsspec.open(self.filepath, mode="rb", **storage_options)

    def _load(self) -> Any:
        import pyarrow.parquet as pq

        load_args = dict(self._spec.config.get("load_args") or {})
        if self.filepath.startswith(("s3://", "gs://", "az://", "abfs://", "http://", "https://")):
            with self._open_fs() as fp:
                return pq.read_table(fp, **load_args)
        return pq.read_table(self.filepath, **load_args)

    def _save(self, payload: Any) -> Any:
        import pyarrow as pa
        import pyarrow.parquet as pq

        save_args = dict(self._spec.config.get("save_args") or {})
        table = payload if isinstance(payload, pa.Table) else pa.Table.from_pandas(payload)
        if self.filepath.startswith(("s3://", "gs://", "az://", "abfs://")):
            try:
                import fsspec  # type: ignore[import-not-found]
            except Exception as exc:  # pragma: no cover
                raise RuntimeError("fsspec is required for remote save") from exc
            storage_options = dict(self._spec.config.get("storage_options") or {})
            with fsspec.open(self.filepath, mode="wb", **storage_options) as fp:
                pq.write_table(table, fp, **save_args)
            return self.filepath
        Path(self.filepath).parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, self.filepath, **save_args)
        return self.filepath

    def _exists(self) -> bool:
        if self.filepath.startswith(("s3://", "gs://", "az://", "abfs://", "http://", "https://")):
            try:
                import fsspec  # type: ignore[import-not-found]

                fs, _ = fsspec.core.url_to_fs(self.filepath, **dict(self._spec.config.get("storage_options") or {}))
                return bool(fs.exists(self.filepath))
            except Exception:  # noqa: BLE001
                return False
        return Path(self.filepath).exists()

    def _describe(self) -> dict[str, Any]:
        return {"filepath": self.filepath, "load_mode": "parquet"}


__all__ = ["ParquetDataset"]
