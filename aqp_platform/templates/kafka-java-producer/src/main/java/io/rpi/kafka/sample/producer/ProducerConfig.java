package io.rpi.kafka.sample.producer;

import io.apicurio.registry.serde.SerdeConfig;
import io.apicurio.registry.serde.avro.AvroKafkaSerializer;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.common.config.SaslConfigs;
import org.apache.kafka.common.config.SslConfigs;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

/**
 * Builds the {@link Properties} object used by {@link org.apache.kafka.clients.producer.KafkaProducer}.
 * Values default to the in-cluster Strimzi listener on port 9094 (SCRAM-SHA-512 over TLS)
 * and Apicurio Registry; environment variables prefixed {@code KAFKA_} override each key.
 */
public final class ProducerConfig {

    private ProducerConfig() {
    }

    public static Properties forEnvironment() {
        Properties props = new Properties();

        props.put(org.apache.kafka.clients.producer.ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
                env("KAFKA_BOOTSTRAP_SERVERS", "trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9094"));
        props.put(org.apache.kafka.clients.producer.ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(org.apache.kafka.clients.producer.ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, AvroKafkaSerializer.class.getName());
        props.put(org.apache.kafka.clients.producer.ProducerConfig.ACKS_CONFIG, "all");
        props.put(org.apache.kafka.clients.producer.ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
        props.put(org.apache.kafka.clients.producer.ProducerConfig.COMPRESSION_TYPE_CONFIG, "snappy");
        props.put(org.apache.kafka.clients.producer.ProducerConfig.LINGER_MS_CONFIG, 10);
        props.put(org.apache.kafka.clients.producer.ProducerConfig.CLIENT_ID_CONFIG,
                env("KAFKA_CLIENT_ID", "kafka-java-producer"));

        // SASL/SSL
        props.put("security.protocol", env("KAFKA_SECURITY_PROTOCOL", "SASL_SSL"));
        props.put(SaslConfigs.SASL_MECHANISM, env("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512"));
        String user = env("KAFKA_SASL_USERNAME", "producer-market");
        String pass = env("KAFKA_SASL_PASSWORD", "");
        props.put(SaslConfigs.SASL_JAAS_CONFIG, String.format(
                "org.apache.kafka.common.security.scram.ScramLoginModule required username=\"%s\" password=\"%s\";",
                user, pass));
        props.put(SslConfigs.SSL_TRUSTSTORE_LOCATION_CONFIG, env("KAFKA_SSL_TRUSTSTORE_LOCATION", "/etc/kafka/ca/truststore.jks"));
        props.put(SslConfigs.SSL_TRUSTSTORE_PASSWORD_CONFIG, env("KAFKA_SSL_TRUSTSTORE_PASSWORD", "changeit"));
        props.put(SslConfigs.SSL_ENDPOINT_IDENTIFICATION_ALGORITHM_CONFIG, "");

        // Apicurio
        props.put(SerdeConfig.REGISTRY_URL,
                env("SCHEMA_REGISTRY_URL", "http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2"));
        props.put(SerdeConfig.AUTO_REGISTER_ARTIFACT, env("SCHEMA_AUTO_REGISTER", "false"));
        props.put(SerdeConfig.EXPLICIT_ARTIFACT_GROUP_ID, env("SCHEMA_GROUP", "default"));
        props.put(SerdeConfig.FIND_LATEST_ARTIFACT, env("SCHEMA_FIND_LATEST", "true"));
        props.put(SerdeConfig.USE_ID, "contentId");
        props.put(SerdeConfig.ENABLE_HEADERS, "true");

        return props;
    }

    private static String env(String key, String fallback) {
        String v = System.getenv(key);
        return (v == null || v.isEmpty()) ? fallback : v;
    }
}
