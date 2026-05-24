"""Apache Hudi batch writer (additive to Iceberg).

Phase 2e of the AQP infra-expansion plan. Provides a thin facade over
the Hudi Spark datasource so AQP code (Celery tasks, dataset kinds,
analysis flows that need upsert semantics) can write a DataFrame /
Arrow table to a Hudi table without re-discovering the configuration
boilerplate.

Importantly: this writer is the ONLY in-process Python path to Hudi
in AQP. Spec validation rejects Iceberg-medallion namespaces before
the Spark write to defend AGENTS rule 3 (single Iceberg write entry
point through ``aqp.data.iceberg_catalog.append_arrow``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from aqp.config import settings
from aqp.data.lakehouse.hudi.namespaces import (
    DEFAULT_HUDI_PREFIX,
    assert_not_iceberg,
    hudi_namespace,
)

logger = logging.getLogger(__name__)


class HudiUnavailableError(RuntimeError):
    """Raised when ``pyspark`` is missing or the Hudi bundle isn't on the classpath."""


class HudiWriteError(RuntimeError):
    """Raised when a Hudi write fails."""


@dataclass(slots=True)
class HudiWriteSpec:
    """Spec for one HudiWriter call.

    The ``namespace`` + ``table`` pair forms the logical address; the
    underlying object-store path is rendered through ``base_uri`` (defaults
    to ``settings.hudi_warehouse_url``).
    """

    namespace: str
    table: str
    record_key_field: str
    precombine_field: str
    partition_path_field: str = ""
    table_type: str = "MERGE_ON_READ"  # MERGE_ON_READ | COPY_ON_WRITE
    operation: str = "upsert"  # upsert | bulk_insert | insert | delete
    base_uri: str = ""  # falls back to settings.hudi_warehouse_url
    extra_options: Mapping[str, str] = field(default_factory=dict)
    hive_sync_enabled: bool = True
    hive_sync_database: str = "aqp_hudi"
    medallion_layer: str = "silver"  # informational only; rule 3 forbids
    #                                 # Hudi from writing through Iceberg's
    #                                 # medallion-validated namespaces.

    def target_uri(self) -> str:
        base = (self.base_uri or settings.hudi_warehouse_url or "").rstrip("/")
        if not base:
            raise HudiWriteError(
                "hudi_warehouse_url unset; configure AQP_HUDI_WAREHOUSE_URL or "
                "topology services > hudi > endpoints.warehouse"
            )
        ns = hudi_namespace(self.namespace)
        return f"{base}/{ns}/{self.table}/"

    def write_options(self) -> dict[str, str]:
        """Render the Hudi datasource options dict."""
        if not self.record_key_field:
            raise HudiWriteError("HudiWriteSpec.record_key_field is required")
        if not self.precombine_field:
            raise HudiWriteError("HudiWriteSpec.precombine_field is required")
        opts: dict[str, str] = {
            "hoodie.table.name": self.table,
            "hoodie.datasource.write.table.type": self.table_type,
            "hoodie.datasource.write.operation": self.operation,
            "hoodie.datasource.write.recordkey.field": self.record_key_field,
            "hoodie.datasource.write.precombine.field": self.precombine_field,
            "hoodie.datasource.write.hive_style_partitioning": "true",
        }
        if self.partition_path_field:
            opts["hoodie.datasource.write.partitionpath.field"] = (
                self.partition_path_field
            )
        if self.hive_sync_enabled:
            opts.update(
                {
                    "hoodie.datasource.hive_sync.enable": "true",
                    "hoodie.datasource.hive_sync.mode": "hms",
                    "hoodie.datasource.hive_sync.database": self.hive_sync_database,
                    "hoodie.datasource.hive_sync.table": self.table,
                    "hoodie.datasource.hive_sync.partition_extractor_class": (
                        "org.apache.hudi.hive.MultiPartKeysValueExtractor"
                    ),
                }
            )
            if settings.hudi_metastore_url:
                opts["hoodie.datasource.hive_sync.jdbcurl"] = settings.hudi_metastore_url
        opts.update({k: str(v) for k, v in self.extra_options.items()})
        return opts


class HudiWriter:
    """Thin facade over the Hudi Spark datasource.

    Construct once per process; reuse across batches. The underlying
    ``SparkSession`` is lazily built on first :meth:`write` call.
    """

    def __init__(self, spec: HudiWriteSpec) -> None:
        assert_not_iceberg(hudi_namespace(spec.namespace))
        if not hudi_namespace(spec.namespace).startswith(DEFAULT_HUDI_PREFIX):
            raise HudiWriteError(
                f"Hudi namespace must start with {DEFAULT_HUDI_PREFIX!r}; got "
                f"{spec.namespace!r}"
            )
        self.spec = spec

    def _spark_session(self) -> Any:
        try:
            from pyspark.sql import SparkSession  # type: ignore[import]
        except ImportError as exc:
            raise HudiUnavailableError(
                "pyspark is not installed; pip install pyspark and pull a "
                "Spark image with the hudi-spark-bundle on the classpath"
            ) from exc
        try:
            session = SparkSession.builder.appName("aqp-hudi-writer").getOrCreate()
        except Exception as exc:  # noqa: BLE001
            raise HudiUnavailableError(
                f"failed to obtain SparkSession: {exc}"
            ) from exc
        return session

    def write(self, payload: Any) -> dict[str, Any]:
        """Write ``payload`` (DataFrame / Arrow table / list of dicts) to Hudi."""
        df = self._normalise_payload(payload)
        opts = self.spec.write_options()
        target = self.spec.target_uri()
        try:
            (
                df.write.format("org.apache.hudi")
                .options(**opts)
                .mode("append")
                .save(target)
            )
        except Exception as exc:  # noqa: BLE001
            raise HudiWriteError(
                f"Hudi write to {target!r} failed: {exc}"
            ) from exc
        logger.info(
            "Hudi write succeeded namespace=%s table=%s rows=%s target=%s",
            self.spec.namespace,
            self.spec.table,
            getattr(df, "count", lambda: "?")(),
            target,
        )
        return {
            "ok": True,
            "namespace": self.spec.namespace,
            "table": self.spec.table,
            "operation": self.spec.operation,
            "target_uri": target,
        }

    def _normalise_payload(self, payload: Any) -> Any:
        """Convert payload into a Spark DataFrame."""
        # Already a Spark DataFrame
        spark_df_cls_name = type(payload).__name__
        if spark_df_cls_name == "DataFrame" and hasattr(payload, "write"):
            return payload
        spark = self._spark_session()
        try:
            import pandas as pd  # type: ignore[import]
        except ImportError:
            pd = None  # type: ignore[assignment]
        if pd is not None and isinstance(payload, pd.DataFrame):
            return spark.createDataFrame(payload)
        try:
            import pyarrow as pa  # type: ignore[import]

            if isinstance(payload, pa.Table):
                if pd is None:
                    raise HudiWriteError(
                        "pandas is required to convert pyarrow Tables for Hudi"
                    )
                return spark.createDataFrame(payload.to_pandas())
        except ImportError:
            pass
        if isinstance(payload, Iterable):
            return spark.createDataFrame(list(payload))
        raise HudiWriteError(
            f"unsupported Hudi payload type {type(payload)!r}; expected "
            "Spark DataFrame, pandas DataFrame, pyarrow Table, or "
            "iterable of dicts"
        )


__all__ = [
    "HudiUnavailableError",
    "HudiWriteError",
    "HudiWriteSpec",
    "HudiWriter",
]
