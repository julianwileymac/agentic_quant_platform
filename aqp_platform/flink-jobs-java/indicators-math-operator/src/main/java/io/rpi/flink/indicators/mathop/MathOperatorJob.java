package io.rpi.flink.indicators.mathop;

import io.rpi.flink.indicators.common.IndicatorPipeline;
import io.rpi.flink.indicators.common.JobCommandLine;
import io.rpi.flink.indicators.common.SinkSchemas;

public final class MathOperatorJob {

    private MathOperatorJob() {
    }

    public static void main(String[] args) throws Exception {
        JobCommandLine.Config cfg = JobCommandLine.parse(args);
        cfg.categoryLabel = "math_operator";
        IndicatorPipeline.run(
                "flink-java-indicators-math-operator",
                cfg,
                new MathOperatorIndicatorFunction(cfg.bufferSize, cfg.windowSizeSec),
                SinkSchemas.FEATURES_INDICATORS_V1);
    }
}
