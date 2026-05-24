package io.rpi.flink.indicators.common;

import org.apache.flink.api.java.utils.ParameterTool;

/**
 * Central helper for parsing the CLI arguments the
 * {@code FlinkSessionJob.spec.args} list supplies. Keeps the indicator jobs
 * terse.
 */
public final class JobCommandLine {

    private JobCommandLine() {
    }

    public static Config parse(String[] args) {
        ParameterTool p = ParameterTool.fromArgs(args);
        Config c = new Config();
        c.bootstrap = p.get("kafka.bootstrap.servers",
                "trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9092");
        c.sourceTopic = p.get("kafka.source.topic", "market.bar.v1");
        c.sinkTopic = p.get("kafka.sink.topic", "features.indicators.v1");
        c.groupId = p.get("kafka.group.id", "flink-java-indicators");
        c.parallelism = p.getInt("parallelism", 2);
        c.checkpointIntervalMs = p.getInt("checkpoint.interval.ms", 60_000);
        c.windowSizeSec = p.getInt("window.size.seconds", 60);
        c.schemaRegistryUrl = p.get("schema.registry.url",
                "http://apicurio-registry.data-services.svc.cluster.local:8080/apis/registry/v2");
        c.bufferSize = p.getInt("buffer.size", 300);
        c.sourceSchemaName = p.get("source.schema.name", "market_bar_v1");
        c.sinkSchemaName = p.get("sink.schema.name", "features_indicators_v1");
        c.categoryLabel = p.get("category.label", "generic");
        c.parameters = p;
        return c;
    }

    public static class Config {
        public String bootstrap;
        public String sourceTopic;
        public String sinkTopic;
        public String groupId;
        public int parallelism;
        public int checkpointIntervalMs;
        public int windowSizeSec;
        public String schemaRegistryUrl;
        public int bufferSize;
        public String sourceSchemaName;
        public String sinkSchemaName;
        public String categoryLabel;
        public ParameterTool parameters;
    }
}
