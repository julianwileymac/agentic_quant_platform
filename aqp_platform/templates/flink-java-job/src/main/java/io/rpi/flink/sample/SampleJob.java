package io.rpi.flink.sample;

import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.api.java.utils.ParameterTool;
import org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema;
import org.apache.flink.connector.kafka.sink.KafkaSink;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;

import java.time.Duration;

/**
 * Reference Flink DataStream job - reads a string topic, adds "-processed" to
 * each record, and writes to an output topic. Extend this class for your own
 * logic. Mirrors the layout of
 * <a href="https://github.com/apache/flink-training">flink-training</a>'s
 * exercise templates.
 */
public final class SampleJob {

    private SampleJob() {
    }

    public static void main(String[] args) throws Exception {
        ParameterTool params = ParameterTool.fromArgs(args);
        String bootstrap = params.get("kafka.bootstrap.servers",
                "trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9092");
        String srcTopic = params.get("kafka.source.topic", "market.bar.v1");
        String dstTopic = params.get("kafka.sink.topic", "features.indicators.v1");
        String groupId  = params.get("kafka.group.id", "flink-java-sample");
        int parallelism = params.getInt("parallelism", 1);

        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.getConfig().setGlobalJobParameters(params);
        env.setParallelism(parallelism);
        env.enableCheckpointing(60_000);

        KafkaSource<String> source = KafkaSource.<String>builder()
                .setBootstrapServers(bootstrap)
                .setGroupId(groupId)
                .setTopics(srcTopic)
                .setStartingOffsets(OffsetsInitializer.latest())
                .setValueOnlyDeserializer(new SimpleStringSchema())
                .build();

        KafkaSink<String> sink = KafkaSink.<String>builder()
                .setBootstrapServers(bootstrap)
                .setRecordSerializer(
                        KafkaRecordSerializationSchema.builder()
                                .setTopic(dstTopic)
                                .setValueSerializationSchema(new SimpleStringSchema())
                                .build())
                .setTransactionalIdPrefix("flink-java-sample-")
                .build();

        WatermarkStrategy<String> wm = WatermarkStrategy.<String>forBoundedOutOfOrderness(Duration.ofSeconds(5))
                .withIdleness(Duration.ofSeconds(30));

        DataStream<String> stream = env.fromSource(source, wm, "kafka-source");
        stream.map(s -> s + "-processed").sinkTo(sink);

        env.execute("flink-java-sample-job");
    }
}
