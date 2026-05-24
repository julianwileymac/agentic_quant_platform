package io.rpi.flink.indicators.common;

/**
 * Canned Avro schema JSON used by every indicator job to serialize output.
 * Inlined so jobs stay self-contained; the authoritative schema lives under
 * {@code flink-jobs/jobs/schemas/features_indicators_v1.avsc} and is
 * compatible with what this produces (extra fields become entries in
 * {@code extras}).
 */
public final class SinkSchemas {

    private SinkSchemas() {
    }

    public static final String FEATURES_INDICATORS_V1 = "{"
            + "\"type\":\"record\","
            + "\"name\":\"FeaturesIndicatorsV1\","
            + "\"namespace\":\"aqp.streaming.features\","
            + "\"fields\":["
            + "{\"name\":\"ts_ns\",\"type\":\"long\"},"
            + "{\"name\":\"window_start_ns\",\"type\":\"long\"},"
            + "{\"name\":\"window_size_sec\",\"type\":\"int\"},"
            + "{\"name\":\"vt_symbol\",\"type\":\"string\"},"
            + "{\"name\":\"close\",\"type\":\"double\"},"
            + "{\"name\":\"compute_ts_ns\",\"type\":\"long\"},"
            + "{\"name\":\"category\",\"type\":[\"null\",\"string\"],\"default\":null},"
            + "{\"name\":\"extras\",\"type\":[\"null\",{\"type\":\"map\",\"values\":\"double\"}],\"default\":null}"
            + "]}";
}
