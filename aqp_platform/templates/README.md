# Sample producer / workload templates

Moved from `rpi_kubernetes/templates/` during the rpi ↔ AQP decoupling.

| Template | Purpose |
| --- | --- |
| `alphavantage-producer/` | Long-running AV REST poller → Kafka (`aqp-streaming`) |
| `kafka-python-producer/` | Python producer scaffold |
| `kafka-python-consumer/` | Python consumer scaffold |
| `kafka-java-producer/` | Java producer scaffold |
| `kafka-java-consumer/` | Java consumer scaffold |
| `flink-java-job/` | Java FlinkSessionJob scaffold |

Install scripts reference these paths under `aqp_platform/templates/`.
Canonical Kafka/Flink manifests:
`aqp_platform/deployments/kubernetes/base-services/{kafka-strimzi,flink}/`.
