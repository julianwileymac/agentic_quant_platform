# Kafka Python Producer Template

Scaffold for building a Kafka producer that publishes Avro records to a topic in
the `trading-kafka` Strimzi cluster. The template mirrors the patterns used by
the sample market-data producers under
[`samples/market-data-producers/python/`](../../samples/market-data-producers/python/)
and the `rpi_k8s_sdk` Python SDK.

## Features

- `confluent-kafka` driver (backed by librdkafka) for throughput.
- Avro serialization via `fastavro` + Apicurio Schema Registry (the `io.confluent`
  wire format remains compatible through the Apicurio ccompat API).
- OpenTelemetry tracing and Prometheus metrics out of the box.
- SCRAM-SHA-512 authentication against the `scram` listener on port 9094.
- Dead-letter fallback on schema/serialization errors.

## Directory layout

```
templates/kafka-python-producer/
├── README.md
├── pyproject.toml
├── Dockerfile
├── src/
│   └── producer/
│       ├── __init__.py
│       ├── __main__.py
│       ├── config.py
│       ├── tracing.py
│       ├── avro_codec.py
│       └── app.py
├── tests/
│   └── test_app.py
└── kubernetes/
    ├── deployment.yaml
    ├── service.yaml
    ├── configmap.yaml
    └── kustomization.yaml
```

## Quick start

1. Copy the template into a new folder:

   ```bash
   cp -r templates/kafka-python-producer my-producer
   ```

2. Replace the placeholder schema / topic names inside
   `src/producer/config.py` and `kubernetes/configmap.yaml`.

3. Build the image:

   ```bash
   docker build -t ghcr.io/julianwiley/my-producer:0.1.0 my-producer/
   ```

4. Apply the kustomization:

   ```bash
   kubectl apply -k my-producer/kubernetes/
   ```

The producer will:

- Load the Avro schema from the Apicurio Registry.
- Open a SCRAM-authenticated session using the `producer-market` KafkaUser
  (Kubernetes Secret `producer-market/password`).
- Emit a span per `produce()` call and a Prometheus counter per message.
- Retry on broker unavailable; write failures to `market.deadletter.v1`.

See [`docs/kafka-clients.md`](../../docs/kafka-clients.md) for the full
walkthrough.
