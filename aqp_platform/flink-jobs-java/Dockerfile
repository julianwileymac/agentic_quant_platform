# =============================================================================
# flink-trading-java image - bundles all per-category shadow JARs
# =============================================================================
# Multi-stage build:
#   1. Build all :indicators-*:shadowJar tasks with the Gradle wrapper
#   2. Copy the resulting JARs into the standard flink:1.20-java11 image
#      alongside the existing plugins.
#
# Build with Buildx for multi-arch:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     -t ghcr.io/julianwiley/flink-trading-java:1.20 \
#     --push flink-jobs-java/
# =============================================================================
FROM eclipse-temurin:17-jdk-jammy AS build

WORKDIR /src
COPY . .
RUN chmod +x gradlew
RUN ./gradlew --no-daemon \
        :indicators-overlap:shadowJar \
        :indicators-momentum:shadowJar \
        :indicators-volume:shadowJar \
        :indicators-volatility:shadowJar \
        :indicators-price-transform:shadowJar \
        :indicators-cycle:shadowJar \
        :indicators-statistic:shadowJar \
        :indicators-patterns:shadowJar \
        :indicators-math-transform:shadowJar \
        :indicators-math-operator:shadowJar

FROM flink:1.20-java11

USER root

RUN mkdir -p /opt/flink-java-jobs

COPY --from=build /src/indicators-overlap/build/libs/*.jar           /opt/flink-java-jobs/indicators-overlap.jar
COPY --from=build /src/indicators-momentum/build/libs/*.jar          /opt/flink-java-jobs/indicators-momentum.jar
COPY --from=build /src/indicators-volume/build/libs/*.jar            /opt/flink-java-jobs/indicators-volume.jar
COPY --from=build /src/indicators-volatility/build/libs/*.jar        /opt/flink-java-jobs/indicators-volatility.jar
COPY --from=build /src/indicators-price-transform/build/libs/*.jar   /opt/flink-java-jobs/indicators-price-transform.jar
COPY --from=build /src/indicators-cycle/build/libs/*.jar             /opt/flink-java-jobs/indicators-cycle.jar
COPY --from=build /src/indicators-statistic/build/libs/*.jar         /opt/flink-java-jobs/indicators-statistic.jar
COPY --from=build /src/indicators-patterns/build/libs/*.jar          /opt/flink-java-jobs/indicators-patterns.jar
COPY --from=build /src/indicators-math-transform/build/libs/*.jar    /opt/flink-java-jobs/indicators-math-transform.jar
COPY --from=build /src/indicators-math-operator/build/libs/*.jar     /opt/flink-java-jobs/indicators-math-operator.jar

RUN chown -R flink:flink /opt/flink-java-jobs

USER flink
