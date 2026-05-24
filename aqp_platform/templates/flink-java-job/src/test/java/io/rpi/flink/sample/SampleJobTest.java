package io.rpi.flink.sample;

import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.test.util.MiniClusterWithClientResource;
import org.apache.flink.runtime.testutils.MiniClusterResourceConfiguration;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Minimal MiniCluster smoke test using the same pattern as
 * {@code flink-training-master}'s {@code HourlyTipsTest}.
 */
class SampleJobTest {

    private static MiniClusterWithClientResource miniCluster;

    @BeforeEach
    void startCluster() throws Exception {
        miniCluster = new MiniClusterWithClientResource(
                new MiniClusterResourceConfiguration.Builder()
                        .setNumberSlotsPerTaskManager(2)
                        .setNumberTaskManagers(1)
                        .build());
        miniCluster.before();
    }

    @AfterEach
    void stopCluster() {
        if (miniCluster != null) {
            miniCluster.after();
        }
    }

    @Test
    void mapAddsSuffix() throws Exception {
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.setParallelism(1);

        List<String> collected = new CopyOnWriteArrayList<>();
        DataStream<String> input = env.fromCollection(Arrays.asList("a", "b", "c"));
        input.map(s -> s + "-processed").executeAndCollect().forEachRemaining(collected::add);

        assertThat(collected).containsExactly("a-processed", "b-processed", "c-processed");
    }
}
