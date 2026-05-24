package io.rpi.flink.indicators.common;

import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericRecord;
import org.apache.flink.api.common.functions.MapFunction;

import java.util.HashMap;
import java.util.Map;

/**
 * Maps {@link IndicatorRecord} to an Avro {@link GenericRecord} that matches
 * {@code features_indicators_v1}. The Avro schema uses nullable unions for
 * every numeric field so different category jobs can write different
 * subsets without breaking each other.
 */
public final class IndicatorRecordToAvro implements MapFunction<IndicatorRecord, GenericRecord> {

    private static final long serialVersionUID = 1L;

    private transient Schema schema;
    private final String schemaJson;

    public IndicatorRecordToAvro(String schemaJson) {
        this.schemaJson = schemaJson;
    }

    @Override
    public GenericRecord map(IndicatorRecord value) {
        if (schema == null) {
            schema = new Schema.Parser().parse(schemaJson);
        }
        GenericRecord record = new GenericData.Record(schema);
        record.put("ts_ns", value.ts_ns);
        record.put("window_start_ns", value.window_start_ns);
        record.put("window_size_sec", value.window_size_sec);
        record.put("vt_symbol", value.vt_symbol);
        record.put("close", value.close);
        record.put("compute_ts_ns", value.compute_ts_ns);

        // Fill known scalar fields when present; extras are serialized into
        // a map field named `extras` on the schema.
        Map<String, Double> extras = new HashMap<>();
        for (Map.Entry<String, Double> entry : value.values.entrySet()) {
            Schema.Field field = schema.getField(entry.getKey());
            if (field == null) {
                extras.put(entry.getKey(), entry.getValue());
            } else {
                record.put(entry.getKey(), entry.getValue());
            }
        }
        if (!extras.isEmpty() && schema.getField("extras") != null) {
            record.put("extras", extras);
        }
        if (schema.getField("category") != null) {
            record.put("category", value.category);
        }
        return record;
    }
}
