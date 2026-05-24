# Flink Java TA-Lib Indicator Jobs

Gradle multi-module project that computes the full TA-Lib indicator catalog
(~158 indicators + ~61 candlestick patterns, organized into 10 per-category
modules) on the `market.bar.v1` stream and publishes enriched
`features.indicators.v1` records to Kafka.

This project **coexists** with the PyFlink `flink-jobs/indicator_compute.py`
job:

| Runtime    | Owns                                             |
|------------|--------------------------------------------------|
| PyFlink    | MVP indicator set (SMA/EMA/RSI/MACD/BB/ATR/OBV)  |
| Java (this)| Full TA-Lib catalog split across 10 category jobs |

## Libraries

- **Flink 1.20** (matches the session cluster image).
- **com.tictactec:ta-lib:0.4.0** - pure-Java port of TA-Lib. Every function
  `TA_SMA`, `TA_RSI`, ..., `TA_CDL3BLACKCROWS` maps 1:1 to a method on
  `com.tictactec.ta.lib.Core`.
- **Apicurio serde** for Avro Kafka IO (Confluent-compat wire format).

## Module layout

```
flink-jobs-java/
├── README.md
├── settings.gradle
├── build.gradle
├── gradle.properties
├── Dockerfile
├── common/                             # shared helpers + POJOs
├── indicators-overlap/                 # SMA, EMA, WMA, DEMA, ..., BBANDS, SAR
├── indicators-momentum/                # ADX, RSI, MACD, STOCH*, ROC*, WILLR, ...
├── indicators-volume/                  # AD, ADOSC, OBV
├── indicators-volatility/              # ATR, NATR, TRANGE
├── indicators-price-transform/         # AVGPRICE, MEDPRICE, TYPPRICE, WCLPRICE
├── indicators-cycle/                   # HT_DCPERIOD, HT_DCPHASE, HT_PHASOR, ...
├── indicators-statistic/               # BETA, CORREL, LINEARREG*, STDDEV, VAR, TSF
├── indicators-patterns/                # ~61 candlestick patterns (CDL*)
├── indicators-math-transform/          # ACOS, ASIN, ATAN, CEIL, ..., SQRT, TANH
└── indicators-math-operator/           # ADD, DIV, MAX, MIN, MINMAX*, MULT, SUB, SUM
```

Each category is a Gradle subproject producing one shadow JAR. Each JAR
registers as a distinct `FlinkSessionJob` under
[kubernetes/base-services/flink/jobs-java/](../kubernetes/base-services/flink/jobs-java/)
so resource usage per category is independent.

## Build

```bash
cd flink-jobs-java
./gradlew clean :common:build shadowJar
```

Or build everything including the multi-arch Docker image with the helper:

```bash
bash bootstrap/scripts/build-flink-jobs-java.sh --push
```

The script uploads per-category JARs to MinIO `s3://flink-jobs/java/<category>.jar`.

## Running tests

Each indicator job has a `ComposedPipeline`-style test harness ported from
[inspiration/flink-training-master/common/src/test/java/org/apache/flink/training/exercises/testing/](../inspiration/flink-training-master/common/src/test/java/org/apache/flink/training/exercises/testing/):

```bash
./gradlew :indicators-momentum:test
```

## Wire format

Input topic `market.bar.v1` is produced by the sample producers under
[samples/market-data-producers/](../samples/market-data-producers/). Output
topic is the shared `features.indicators.v1`, where each category job writes
only the fields it owns (null for the others). The downstream normalize and
scanner-alert jobs already tolerate partial records.

See [`docs/ta-indicators.md`](../docs/ta-indicators.md) for the full
indicator-to-job mapping and tuning guide.
