# Flink Java Job Template

Gradle module template for a DataStream-API Flink job that reads Avro records
from `trading-kafka`, performs a stateful transform, and writes Avro to an
output topic. The module layout mirrors
[inspiration/flink-training-master/hourly-tips](../../inspiration/flink-training-master/hourly-tips)
and shares the `common` testing rig (`ComposedPipeline`,
`ParallelTestSource`, `TestSink`).

## Layout

```
templates/flink-java-job/
├── README.md
├── build.gradle
├── settings.gradle
├── gradle.properties
├── src/main/
│   ├── java/io/rpi/flink/sample/
│   │   ├── SampleJob.java
│   │   └── MarketBar.java
│   └── resources/log4j2.properties
├── src/test/java/io/rpi/flink/sample/
│   └── SampleJobTest.java
└── kubernetes/flinksessionjob.yaml
```

## Quick start

```bash
cp -r templates/flink-java-job flink-jobs-java/my-job
# add ':my-job' to flink-jobs-java/settings.gradle
cd flink-jobs-java
./gradlew :my-job:shadowJar
```

Upload the shadow JAR to MinIO (the build-flink-jobs-java.sh script handles
this), then submit the CR under `kubernetes/base-services/flink/jobs-java/`.
