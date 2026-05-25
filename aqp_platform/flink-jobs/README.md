# PyFlink trading jobs

Status: **active** — owned by `agentic_quant_platform/aqp_platform/`.

PyFlink job sources, Avro schemas, and the `flink-trading` container image build
context. Lifted from `rpi_kubernetes/flink-jobs/` during the rpi ↔ AQP decoupling.

## Related paths

| Artifact | Location |
| --- | --- |
| FlinkSessionJob CRs | `aqp_platform/deployments/kubernetes/base-services/flink/jobs/` |
| Java TA-Lib jobs | `aqp_platform/flink-jobs-java/` |
| Session cluster + operator values | `aqp_platform/deployments/kubernetes/base-services/flink/` |
| Build + MinIO upload | `aqp_platform/scripts/cluster_install/build-flink-jobs.sh` |
| Cluster install | `aqp_platform/scripts/cluster_install/install-flink.sh` |

## Build

```bash
# From agentic_quant_platform repo root
bash aqp_platform/scripts/cluster_install/build-flink-jobs.sh --push
```

Canonical doc: [aqp_docs/docs/concepts/data/streaming.md](../../aqp_docs/docs/concepts/data/streaming.md).
