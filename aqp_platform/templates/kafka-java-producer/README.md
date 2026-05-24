# Kafka Java Producer Template

Gradle scaffold for a Java Kafka producer that publishes Avro records to the
`trading-kafka` Strimzi cluster via Apicurio Schema Registry (Confluent-compatible
wire format).

## Features

- `org.apache.kafka:kafka-clients` with idempotent + acks=all semantics.
- Apicurio Avro serializer (`io.apicurio:apicurio-registry-serdes-avro-serde`).
- OpenTelemetry Java Agent auto-instrumentation for Kafka + HTTP calls.
- SCRAM-SHA-512 authentication against listener 9094.
- Gradle shadow JAR output; Dockerfile packages the agent alongside the fat jar.

## Quick start

```bash
cp -r templates/kafka-java-producer my-java-producer
cd my-java-producer
./gradlew shadowJar
docker build -t ghcr.io/julianwiley/my-java-producer:0.1.0 .
kubectl apply -k kubernetes/
```

## Layout

```
templates/kafka-java-producer/
├── README.md
├── build.gradle
├── settings.gradle
├── gradle.properties
├── gradle/wrapper/gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── src/main/
│   ├── java/io/rpi/kafka/sample/producer/
│   │   ├── ProducerApp.java
│   │   └── ProducerConfig.java
│   └── resources/
│       └── log4j2.properties
├── Dockerfile
└── kubernetes/
    ├── configmap.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── kustomization.yaml
```
