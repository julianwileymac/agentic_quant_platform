package io.rpi.flink.indicators.common;

import org.apache.avro.generic.GenericRecord;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;

import java.time.Duration;

/**
 * Boilerplate for every category job - builds the source + keyBy + process
 * + sink chain so each {@code indicators-*} module only has to supply the
 * {@link KeyedProcessFunction} that actually calls TA-Lib.
 *
 * <p>The mermaid-worthy pipeline diagram:</p>
 * <pre>
 * KafkaSource&lt;GenericRecord&gt;           (market.bar.v1)
 *     -&gt; map(GenericRecord -&gt; MarketBar)
 *     -&gt; keyBy(vt_symbol)
 *     -&gt; process(KeyedProcessFunction)   (per-category TA-Lib calls)
 *     -&gt; filter(non-empty IndicatorRecord)
 *     -&gt; map(IndicatorRecord -&gt; GenericRecord)
 *     -&gt; KafkaSink&lt;GenericRecord&gt;       (features.indicators.v1)
 * </pre>
 */
public final class IndicatorPipeline {

    private IndicatorPipeline() {
    }

    public static void run(
            String jobName,
            JobCommandLine.Config cfg,
            KeyedProcessFunction<String, MarketBar, IndicatorRecord> indicatorFn,
            String sinkSchemaJson
    ) throws Exception {
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(cfg.parallelism);
        env.getConfig().setGlobalJobParameters(cfg.parameters);
        env.enableCheckpointing(cfg.checkpointIntervalMs);

        WatermarkStrategy<GenericRecord> wm = WatermarkStrategy
                .<GenericRecord>forBoundedOutOfOrderness(Duration.ofSeconds(5))
                .withIdleness(Duration.ofSeconds(30))
                .withTimestampAssigner((record, ts) -> {
                    Object v = record.get("ts_ns");
                    return v instanceof Number ? ((Number) v).longValue() / 1_000_000L : ts;
                });

        DataStream<GenericRecord> avroStream = env.fromSource(
                KafkaIO.buildAvroSource(cfg), wm, "kafka-" + cfg.sourceTopic);

        DataStream<MarketBar> bars = avroStream.map(new AvroGenericRecordToBar());

        DataStream<IndicatorRecord> indicators = bars
                .keyBy(bar -> bar.vt_symbol)
                .process(indicatorFn)
                .name("ta-lib-" + cfg.categoryLabel);

        indicators
                .filter(record -> record != null && !record.isEmpty())
                .map(new IndicatorRecordToAvro(sinkSchemaJson))
                .sinkTo(KafkaIO.buildAvroSink(cfg))
                .name("kafka-" + cfg.sinkTopic);

        env.execute(jobName);
    }
}
