# Kafka Python Consumer Template

Scaffold for an async Kafka consumer that reads Avro records from the
`trading-kafka` Strimzi cluster. Uses `aiokafka` for cooperative concurrency
(each poll yields to the event loop so a single worker can sustain tens of
thousands of messages/sec on a Raspberry Pi).

## Features

- `aiokafka` with manual offset commit and consumer-group management.
- Apicurio-backed Avro decoding (ccompat format: magic + schema id + body).
- OpenTelemetry tracing, Prometheus metrics, graceful shutdown.
- SCRAM-SHA-512 authentication as `consumer-management` (override via env).

## Quick start

```bash
cp -r templates/kafka-python-consumer my-consumer
docker build -t ghcr.io/julianwiley/my-consumer:0.1.0 my-consumer/
kubectl apply -k my-consumer/kubernetes/
```

See [`docs/kafka-clients.md`](../../docs/kafka-clients.md) for the full
walkthrough.
