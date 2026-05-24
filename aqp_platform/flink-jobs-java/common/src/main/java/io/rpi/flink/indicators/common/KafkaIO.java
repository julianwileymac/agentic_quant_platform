package io.rpi.flink.indicators.common;

import io.apicurio.registry.serde.SerdeConfig;
import io.apicurio.registry.serde.avro.AvroKafkaDeserializer;
import io.apicurio.registry.serde.avro.AvroKafkaSerializer;
import org.apache.avro.generic.GenericRecord;
import org.apache.flink.api.common.serialization.DeserializationSchema;
import org.apache.flink.api.common.serialization.SerializationSchema;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema;
import org.apache.flink.connector.kafka.sink.KafkaSink;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.Properties;

/**
 * Builds Kafka sources + sinks using the Apicurio Avro serde. Mirrors
 * {@code common.kafka} in the PyFlink jobs so the Java and Python runtimes
 * stay interoperable.
 */
public final class KafkaIO {

    private KafkaIO() {
    }

    public static KafkaSource<GenericRecord> buildAvroSource(JobCommandLine.Config cfg) {
        Map<String, Object> serdeConfig = new HashMap<>();
        serdeConfig.put(SerdeConfig.REGISTRY_URL, cfg.schemaRegistryUrl);
        serdeConfig.put(SerdeConfig.USE_ID, "contentId");
        serdeConfig.put(SerdeConfig.ENABLE_HEADERS, "true");

        return KafkaSource.<GenericRecord>builder()
                .setBootstrapServers(cfg.bootstrap)
                .setGroupId(cfg.groupId)
                .setTopics(cfg.sourceTopic)
                .setStartingOffsets(OffsetsInitializer.latest())
                .setValueOnlyDeserializer(new ApicurioAvroDeserializer(serdeConfig))
                .build();
    }

    public static KafkaSink<GenericRecord> buildAvroSink(JobCommandLine.Config cfg) {
        Map<String, Object> serdeConfig = new HashMap<>();
        serdeConfig.put(SerdeConfig.REGISTRY_URL, cfg.schemaRegistryUrl);
        serdeConfig.put(SerdeConfig.AUTO_REGISTER_ARTIFACT, "false");
        serdeConfig.put(SerdeConfig.EXPLICIT_ARTIFACT_GROUP_ID, "default");
        serdeConfig.put(SerdeConfig.SCHEMA_ARTIFACT_ID, cfg.sinkSchemaName);
        serdeConfig.put(SerdeConfig.FIND_LATEST_ARTIFACT, "true");
        serdeConfig.put(SerdeConfig.USE_ID, "contentId");
        serdeConfig.put(SerdeConfig.ENABLE_HEADERS, "true");

        return KafkaSink.<GenericRecord>builder()
                .setBootstrapServers(cfg.bootstrap)
                .setRecordSerializer(
                        KafkaRecordSerializationSchema.<GenericRecord>builder()
                                .setTopic(cfg.sinkTopic)
                                .setValueSerializationSchema(new ApicurioAvroSerializer(serdeConfig))
                                .build())
                .setTransactionalIdPrefix("flink-java-indicators-" + cfg.categoryLabel + "-")
                .build();
    }

    private static final class ApicurioAvroDeserializer implements DeserializationSchema<GenericRecord> {
        private static final long serialVersionUID = 1L;

        private final Map<String, Object> serdeConfig;
        private transient AvroKafkaDeserializer<GenericRecord> inner;

        ApicurioAvroDeserializer(Map<String, Object> serdeConfig) {
            this.serdeConfig = serdeConfig;
        }

        @Override
        public GenericRecord deserialize(byte[] message) throws IOException {
            ensureInitialized();
            return inner.deserialize(null, message);
        }

        @Override
        public boolean isEndOfStream(GenericRecord nextElement) {
            return false;
        }

        @Override
        public TypeInformation<GenericRecord> getProducedType() {
            return TypeInformation.of(GenericRecord.class);
        }

        private void ensureInitialized() {
            if (inner == null) {
                inner = new AvroKafkaDeserializer<>();
                Properties p = new Properties();
                p.putAll(serdeConfig);
                inner.configure(new HashMap<>(serdeConfig), false);
            }
        }
    }

    private static final class ApicurioAvroSerializer implements SerializationSchema<GenericRecord> {
        private static final long serialVersionUID = 1L;

        private final Map<String, Object> serdeConfig;
        private transient AvroKafkaSerializer<GenericRecord> inner;

        ApicurioAvroSerializer(Map<String, Object> serdeConfig) {
            this.serdeConfig = serdeConfig;
        }

        @Override
        public byte[] serialize(GenericRecord element) {
            ensureInitialized();
            return inner.serialize(null, element);
        }

        private void ensureInitialized() {
            if (inner == null) {
                inner = new AvroKafkaSerializer<>();
                inner.configure(new HashMap<>(serdeConfig), false);
            }
        }
    }
}
