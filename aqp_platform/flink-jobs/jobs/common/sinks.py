"""Sink builders: JDBC (PostgreSQL), Parquet-on-S3, VictoriaMetrics remote-write.

The Flink DataStream Python API exposes JDBC + file sinks via the
``pyflink.datastream.connectors`` package (which internally calls the
Java connectors shipped in the custom Flink image). This module thinly
wraps them so jobs don't have to re-learn the builder pattern.

VictoriaMetrics ingestion uses a plain HTTP ``RichSinkFunction`` that
POSTs Prometheus remote-write batches. No Java connector needed; we
stick with the Python sink for portability.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def build_jdbc_sink(
    url: str,
    table: str,
    columns: list[str],
    *,
    username: str,
    password: str,
    driver: str = "org.postgresql.Driver",
    batch_size: int = 200,
    batch_interval_ms: int = 1_000,
    upsert_keys: list[str] | None = None,
) -> Any:
    """Return a Flink JDBC sink function for the supplied table.

    ``upsert_keys`` triggers ``ON CONFLICT (...) DO UPDATE`` semantics
    when non-empty; leave ``None`` for append-only inserts.
    """
    from pyflink.datastream.connectors.jdbc import (  # type: ignore[import]
        JdbcConnectionOptions,
        JdbcExecutionOptions,
        JdbcSink,
    )

    placeholders = ",".join(["?"] * len(columns))
    col_list = ",".join(columns)
    if upsert_keys:
        updates = ",".join(f"{c}=EXCLUDED.{c}" for c in columns if c not in upsert_keys)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT ({','.join(upsert_keys)}) DO UPDATE SET {updates}"
        )
    else:
        sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    connection_options = (
        JdbcConnectionOptions.JdbcConnectionOptionsBuilder()
        .with_driver_name(driver)
        .with_url(url)
        .with_user_name(username)
        .with_password(password)
        .build()
    )
    execution_options = (
        JdbcExecutionOptions.builder()
        .with_batch_size(batch_size)
        .with_batch_interval_ms(batch_interval_ms)
        .with_max_retries(3)
        .build()
    )
    return JdbcSink.sink(
        sql=sql,
        type_info=None,  # jobs must pass row-level binder explicitly
        jdbc_connection_options=connection_options,
        jdbc_execution_options=execution_options,
    )


def build_parquet_sink(
    output_path: str,
    *,
    part_prefix: str = "part",
    rolling_interval_ms: int = 60_000,
) -> Any:
    """Return a FileSystem streaming file sink that writes Parquet to MinIO.

    ``output_path`` should be an ``s3://bucket/prefix/`` URL. Flink's
    ``StreamingFileSink`` rolls parts by size/time and commits atomically
    via the two-phase commit pattern.
    """
    from pyflink.common import Duration  # type: ignore[import]
    from pyflink.datastream.connectors.file_system import (  # type: ignore[import]
        FileSink,
        OutputFileConfig,
        RollingPolicy,
    )
    from pyflink.datastream.formats.parquet import AvroParquetWriters  # type: ignore[import]

    output_config = (
        OutputFileConfig.builder().with_part_prefix(part_prefix).with_part_suffix(".parquet").build()
    )
    rolling_policy = (
        RollingPolicy.default_rolling_policy()
        .with_rollover_interval(Duration.of_millis(rolling_interval_ms))
        .with_max_part_size(256 * 1024 * 1024)
        .build()
    )
    return (
        FileSink.for_bulk_format(
            output_path,
            AvroParquetWriters.for_generic_record(None),  # schema injected by job
        )
        .with_output_file_config(output_config)
        .with_rolling_policy(rolling_policy)
        .build()
    )


class VictoriaMetricsSink:
    """Stateless HTTP sink posting records to VictoriaMetrics remote-write.

    The job passes a ``formatter`` callable that turns each incoming
    record into one or more ``(metric_name, labels, timestamp_ms, value)``
    tuples. Because VictoriaMetrics accepts both Prometheus and
    OpenMetrics exposition formats, we emit the OpenMetrics text form
    for simplicity; full Protobuf remote-write can be added later with
    ``prometheus_client.core.Sample`` + ``remote_pb2``.
    """

    def __init__(
        self,
        write_url: str,
        formatter: Callable[[Any], list[tuple[str, dict[str, str], int, float]]],
    ) -> None:
        self.write_url = write_url
        self.formatter = formatter

    def open(self, *_: Any) -> None:
        import requests  # type: ignore[import]

        self._session = requests.Session()

    def invoke(self, record: Any, *_: Any) -> None:  # noqa: D401 - Flink API
        lines: list[str] = []
        for metric, labels, ts_ms, value in self.formatter(record):
            label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
            lines.append(f"{metric}{{{label_str}}} {value} {ts_ms}")
        if not lines:
            return
        try:
            self._session.post(
                self.write_url.rstrip("/") + "/api/v1/import/prometheus",
                data="\n".join(lines).encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=5.0,
            )
        except Exception:  # noqa: BLE001
            logger.exception("VictoriaMetrics remote-write failed")

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass


def build_victoriametrics_sink(
    write_url: str,
    formatter: Callable[[Any], list[tuple[str, dict[str, str], int, float]]],
) -> VictoriaMetricsSink:
    """Convenience factory so job code reads symmetric to the other sinks."""
    return VictoriaMetricsSink(write_url=write_url, formatter=formatter)


__all__ = [
    "VictoriaMetricsSink",
    "build_jdbc_sink",
    "build_parquet_sink",
    "build_victoriametrics_sink",
]
