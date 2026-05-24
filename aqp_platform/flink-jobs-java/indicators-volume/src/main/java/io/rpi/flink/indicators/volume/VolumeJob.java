package io.rpi.flink.indicators.volume;

import io.rpi.flink.indicators.common.IndicatorPipeline;
import io.rpi.flink.indicators.common.JobCommandLine;
import io.rpi.flink.indicators.common.SinkSchemas;

public final class VolumeJob {

    private VolumeJob() {
    }

    public static void main(String[] args) throws Exception {
        JobCommandLine.Config cfg = JobCommandLine.parse(args);
        cfg.categoryLabel = "volume";
        IndicatorPipeline.run(
                "flink-java-indicators-volume",
                cfg,
                new VolumeIndicatorFunction(cfg.bufferSize, cfg.windowSizeSec),
                SinkSchemas.FEATURES_INDICATORS_V1);
    }
}
