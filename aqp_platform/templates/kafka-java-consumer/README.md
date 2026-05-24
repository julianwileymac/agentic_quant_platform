# Kafka Java Consumer Template

Gradle scaffold for a Java Kafka consumer that reads Avro records via
Apicurio Registry. Uses OpenTelemetry Java Agent for auto-instrumentation
and micrometer + Prometheus for metrics.

## Quick start

```bash
cp -r templates/kafka-java-consumer my-java-consumer
cd my-java-consumer
./gradlew shadowJar
docker build -t ghcr.io/julianwiley/my-java-consumer:0.1.0 .
kubectl apply -k kubernetes/
```
