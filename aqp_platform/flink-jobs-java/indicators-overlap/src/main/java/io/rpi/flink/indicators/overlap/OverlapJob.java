package io.rpi.flink.indicators.overlap;

import io.rpi.flink.indicators.common.IndicatorPipeline;
import io.rpi.flink.indicators.common.JobCommandLine;
import io.rpi.flink.indicators.common.SinkSchemas;

/**
 * Job entrypoint - wires the overlap indicator function through the shared
 * pipeline helper. Submitted via
 * {@code kubernetes/base-services/flink/jobs-java/overlap.yaml}.
 */
public final class OverlapJob {

    private OverlapJob() {
    }

    public static void main(String[] args) throws Exception {
        JobCommandLine.Config cfg = JobCommandLine.parse(args);
        cfg.categoryLabel = "overlap";
        IndicatorPipeline.run(
                "flink-java-indicators-overlap",
                cfg,
                new OverlapIndicatorFunction(cfg.bufferSize, cfg.windowSizeSec),
                SinkSchemas.FEATURES_INDICATORS_V1);
    }
}
