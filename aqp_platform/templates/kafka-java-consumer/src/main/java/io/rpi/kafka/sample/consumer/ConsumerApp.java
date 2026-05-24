package io.rpi.kafka.sample.consumer;

import io.apicurio.registry.serde.SerdeConfig;
import io.apicurio.registry.serde.avro.AvroKafkaDeserializer;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.prometheus.PrometheusConfig;
import io.micrometer.prometheus.PrometheusMeterRegistry;
import org.apache.avro.generic.GenericRecord;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.clients.consumer.ConsumerRecords;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.common.config.SaslConfigs;
import org.apache.kafka.common.config.SslConfigs;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.Properties;
import com.sun.net.httpserver.HttpServer;

public final class ConsumerApp {

    private static final Logger LOG = LoggerFactory.getLogger(ConsumerApp.class);
    private static final int METRICS_PORT = 9303;

    private ConsumerApp() {
    }

    public static void main(String[] args) throws Exception {
        Properties props = new Properties();
        props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
                env("KAFKA_BOOTSTRAP_SERVERS", "trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9094"));
        props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG, StringDeserializer.class.getName());
        props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG, AvroKafkaDeserializer.class.getName());
        props.put(ConsumerConfig.GROUP_ID_CONFIG, env("KAFKA_GROUP_ID", "kafka-java-consumer"));
        props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, env("KAFKA_AUTO_OFFSET_RESET", "latest"));
        props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, "false");
        props.put(ConsumerConfig.MAX_POLL_RECORDS_CONFIG,
                Integer.valueOf(env("KAFKA_MAX_POLL_RECORDS", "500")));

        props.put("security.protocol", env("KAFKA_SECURITY_PROTOCOL", "SASL_SSL"));
        props.put(SaslConfigs.SASL_MECHANISM, env("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512"));
        props.put(SaslConfigs.SASL_JAAS_CONFIG, String.format(
                "org.apache.kafka.common.security.scram.ScramLoginModule required username=\"%s\" password=\"%s\";",
                env("KAFKA_SASL_USERNAME", "consumer-management"),
                env("KAFKA_SASL_PASSWORD", "")));
        props.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG,
                env("KAFKA_SSL_TRUSTSTORE_LOCATION", "/etc/kafka/ca/truststore.jks"));
        props.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG,
                env("KAFKA_SSL_TRUSTSTORE_PASSWORD", "changeit"));
        props.put(SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG, "");

        props.put(SerdeConfig.REGISTRY_URL,
                env("SCHEMA_REGISTRY_URL", "http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2"));
        props.put(SerdeConfig.USE_ID, "contentId");
        props.put(SerdeConfig.ENABLE_HEADERS, "true");

        String topicList = env("KAFKA_TOPICS", "market.bar.v1");

        PrometheusMeterRegistry registry = new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        Metrics.addRegistry(registry);
        Counter consumed = registry.counter("kafka_consumer_messages_consumed_total");
        startMetricsServer(registry);

        try (KafkaConsumer<String, GenericRecord> consumer = new KafkaConsumer<>(props)) {
            consumer.subscribe(Arrays.asList(topicList.split(",")));
            LOG.info("subscribed topics={}", topicList);
            while (!Thread.currentThread().isInterrupted()) {
                ConsumerRecords<String, GenericRecord> records = consumer.poll(Duration.ofSeconds(1));
                if (records.isEmpty()) {
                    continue;
                }
                for (ConsumerRecord<String, GenericRecord> record : records) {
                    LOG.debug("topic={} partition={} offset={} key={} value={}",
                            record.topic(), record.partition(), record.offset(), record.key(), record.value());
                    consumed.increment();
                }
                consumer.commitSync();
            }
        }
    }

    private static String env(String key, String fallback) {
        String v = System.getenv(key);
        return (v == null || v.isEmpty()) ? fallback : v;
    }

    private static void startMetricsServer(PrometheusMeterRegistry registry) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress(METRICS_PORT), 0);
        server.createContext("/metrics", exchange -> {
            byte[] body = registry.scrape().getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(body);
            }
        });
        server.setExecutor(null);
        server.start();
        LOG.info("Prometheus metrics on :{}/metrics", METRICS_PORT);
    }
}
