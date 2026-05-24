# Apache Hudi (additive lakehouse)

Phase 2e of the AQP infra-expansion plan added Apache Hudi as an
ADDITIVE second writer for upsert-heavy partitions. Iceberg remains
the canonical lakehouse write path (AGENTS rule 3): every write to
Iceberg goes through `aqp.data.iceberg_catalog.append_arrow`. Hudi
tables live under their own `aqp_hudi_*` namespace prefix and are
NEVER written through `append_arrow`.

## When to use which

- **Iceberg** (default): append-only history, broad analytics,
  Trino + Spark + Flink shared catalog, gold-tier products.
- **Hudi** (this package): upsert-heavy partitions where
  late-arriving / corrected market data has to merge in place
  (per-symbol tick streams, intraday corrections, vendor late
  arrivals).

## Surface

| Artefact | Purpose |
|---|---|
| [`aqp/data/lakehouse/hudi/namespaces.py`](../aqp/data/lakehouse/hudi/namespaces.py) | `aqp_hudi_*` prefix contract + `assert_not_iceberg` guard. |
| [`aqp/data/lakehouse/hudi/hudi_writer.py`](../aqp/data/lakehouse/hudi/hudi_writer.py) | PySpark batch writer (DataFrame / Arrow -> Hudi). |
| [`aqp/data/lakehouse/hudi/hudi_streamer.py`](../aqp/data/lakehouse/hudi/hudi_streamer.py) | Continuous Kafka -> Hudi via Spark Operator. |
| [`aqp/data/datasets/kinds/hudi.py`](../aqp/data/datasets/kinds/hudi.py) | Kedro-style dataset kind (`kind="hudi"`). |
| `data.lakehouse.hudi.{list_tables,upsert_arrow,start_streamer,stop_streamer}` | MCP tools. |

## Kubernetes deployment

- [`deployments/kubernetes/mlops/spark-operator/`](../deployments/kubernetes/mlops/spark-operator/)
  — Kubeflow Spark Operator (Helm).
- [`deployments/kubernetes/mlops/hudi/`](../deployments/kubernetes/mlops/hudi/)
  — `aqp-hudi-streamer-properties` ConfigMap + warehouse bootstrap
  Job (creates `s3://aqp-lakehouse/hudi/`).

The `HudiStreamerLauncher` submits `SparkApplication` CRs into the
`aqp-mlops` namespace so the operator drives HoodieStreamer
continuously against Redpanda / Strimzi topics.

## Defending rule 3

Two layers:

1. `assert_not_iceberg(table_name)` at every Hudi write entry-point
   refuses any name starting with `aqp_bronze_`/`aqp_silver_`/
   `aqp_gold_`.
2. `iceberg_catalog._validate_layer_prefix` rejects Hudi-style
   identifiers (everything that doesn't match a medallion-tagged
   namespace).

Together they keep the two writers strictly separated even if a
caller misconfigures a `HudiSpec`.

## Topology entry

`services > hudi` + `services > spark-operator` (cluster
`lakehouse.hudi`, namespace `aqp-lakehouse` / `aqp-mlops`). The
`hudi` service is `workload: external` (it has no Kubernetes
Deployment of its own — only a warehouse path on MinIO).
