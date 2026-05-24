# Redpanda

Phase 2a of the AQP infra-expansion plan added Redpanda alongside
the existing Strimzi Kafka cluster (per plan question 2 =
side-by-side). Both clusters speak the Kafka API; AQP code routes
topics by name prefix in
[`aqp/streaming/clusters.py`](../aqp/streaming/clusters.py).

## Topic-prefix routing

| Prefix | Cluster |
|---|---|
| `market.l1.*` | Redpanda |
| `market.l2.*` | Redpanda |
| `execution.orders.*` | Redpanda |
| `agentic.state.*` | Redpanda |
| everything else | Strimzi |

The [`KafkaAvroProducer`](../aqp/streaming/kafka_producer.py) accepts
a `cluster=` kwarg or `auto_route=True` to dispatch per-record. The
[`NativeKafkaAdmin`](../aqp/streaming/admin/kafka_admin.py) accepts
the same kwarg.

## DataMCP tools

| Tool | Purpose |
|---|---|
| `data.streaming.kafka.list_topics` | List Strimzi topics (legacy default). |
| `data.streaming.redpanda.list_topics` | List Redpanda topics. |
| `data.streaming.clusters.list` | Enumerate registered clusters. |
| `data.streaming.clusters.resolve` | Look up which cluster owns a topic. |

## Kubernetes deployment

[`deployments/kubernetes/base-services/redpanda/`](../deployments/kubernetes/base-services/redpanda/).
Installed via [`scripts/cluster_install/install-redpanda.sh`](../scripts/cluster_install/install-redpanda.sh):

```bash
./scripts/cluster_install/install-redpanda.sh
```

Cluster CR pins `statefulset.replicas=3`, hard pod-anti-affinity,
tiered storage offload to `s3://redpanda-offload/` on MinIO.

## Topology entry

`topology.yaml` -> `services > redpanda` (cluster `streaming.redpanda`,
namespace `aqp-streaming`, port 9092). Endpoints: `bootstrap`,
`admin`, `schema_registry`.
