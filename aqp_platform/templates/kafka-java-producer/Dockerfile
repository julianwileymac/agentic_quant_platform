# syntax=docker/dockerfile:1.6
FROM eclipse-temurin:17-jdk-jammy AS build

WORKDIR /src
COPY gradlew gradle/wrapper/gradle-wrapper.properties ./
COPY settings.gradle build.gradle gradle.properties ./
COPY src ./src
RUN chmod +x gradlew
RUN ./gradlew --no-daemon shadowJar

FROM eclipse-temurin:17-jre-jammy

ARG OTEL_AGENT_VERSION=2.5.0
RUN mkdir -p /opt/otel \
    && curl -fsSL -o /opt/otel/opentelemetry-javaagent.jar \
        https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${OTEL_AGENT_VERSION}/opentelemetry-javaagent.jar

WORKDIR /app
COPY --from=build /src/build/libs/*.jar /app/app.jar

RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app /opt/otel
USER app

EXPOSE 9302

ENV JAVA_TOOL_OPTIONS="-javaagent:/opt/otel/opentelemetry-javaagent.jar -Dotel.metrics.exporter=none"
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
