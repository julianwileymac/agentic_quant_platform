"""Apache Hudi :class:`BaseDataset`.

Phase 2e of the AQP infra-expansion plan. Reads Hudi tables via
PySpark; writes via :class:`aqp.data.lakehouse.hudi.hudi_writer.HudiWriter`.

Spec config schema::

    {
      "namespace": "market_l1",       # rendered as aqp_hudi_market_l1
      "table": "market_l1_corrected",
      "record_key_field": "vt_symbol",
      "precombine_field": "ts_ns",
      "partition_path_field": "exchange,date_str",
      "table_type": "MERGE_ON_READ",  # or COPY_ON_WRITE
      "operation": "upsert",          # upsert | bulk_insert | insert | delete
      "base_uri": "s3://aqp-lakehouse/hudi/",
      "extra_options": {...},
      "snapshot_query": "SELECT ...",  # optional read override
    }

Iceberg remains the canonical lakehouse write path (rule 3); this
kind is the ONLY sanctioned in-process write path to Hudi.
"""
from __future__ import annotations

from typing import Any

from aqp.data.datasets.base import BaseDataset
from aqp.data.lakehouse.hudi.hudi_writer import HudiWriter, HudiWriteSpec
from aqp.data.lakehouse.hudi.namespaces import hudi_namespace


class HudiDataset(BaseDataset):
    kind = "hudi"
    writable = True

    def _validate_spec(self) -> None:
        cfg = self._spec.config
        for key in ("namespace", "table", "record_key_field", "precombine_field"):
            if not str(cfg.get(key) or "").strip():
                raise ValueError(f"HudiDataset requires config.{key}")

    def _hudi_write_spec(self) -> HudiWriteSpec:
        cfg = self._spec.config
        return HudiWriteSpec(
            namespace=str(cfg["namespace"]),
            table=str(cfg["table"]),
            record_key_field=str(cfg["record_key_field"]),
            precombine_field=str(cfg["precombine_field"]),
            partition_path_field=str(cfg.get("partition_path_field") or ""),
            table_type=str(cfg.get("table_type") or "MERGE_ON_READ"),
            operation=str(cfg.get("operation") or "upsert"),
            base_uri=str(cfg.get("base_uri") or ""),
            extra_options=dict(cfg.get("extra_options") or {}),
            hive_sync_enabled=bool(cfg.get("hive_sync_enabled", True)),
        )

    # ---------------------------------------------------------- read
    def _load(self) -> Any:
        cfg = self._spec.config
        snapshot_query = cfg.get("snapshot_query")
        try:
            from pyspark.sql import SparkSession  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "HudiDataset.load requires pyspark with the hudi-spark-bundle"
            ) from exc
        spark = SparkSession.builder.appName("aqp-hudi-reader").getOrCreate()
        target_uri = self._hudi_write_spec().target_uri()
        if snapshot_query:
            df = spark.read.format("org.apache.hudi").load(target_uri)
            df.createOrReplaceTempView(self._view_name())
            return spark.sql(str(snapshot_query)).toPandas()
        return spark.read.format("org.apache.hudi").load(target_uri).toPandas()

    def _view_name(self) -> str:
        cfg = self._spec.config
        ns = hudi_namespace(str(cfg["namespace"]))
        return f"{ns}_{cfg['table']}".replace(".", "_")

    # ---------------------------------------------------------- write
    def _save(self, payload: Any) -> Any:
        writer = HudiWriter(self._hudi_write_spec())
        return writer.write(payload)

    # ---------------------------------------------------------- describe
    def _describe(self) -> dict[str, Any]:
        cfg = self._spec.config
        return {
            "namespace": cfg.get("namespace"),
            "table": cfg.get("table"),
            "record_key_field": cfg.get("record_key_field"),
            "precombine_field": cfg.get("precombine_field"),
            "table_type": cfg.get("table_type") or "MERGE_ON_READ",
            "operation": cfg.get("operation") or "upsert",
            "load_mode": "hudi_spark",
        }

    def _exists(self) -> bool:
        cfg = self._spec.config
        return bool(cfg.get("namespace") and cfg.get("table"))


__all__ = ["HudiDataset"]
