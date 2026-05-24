# =============================================================================
# flink-trading PyFlink image for the AQP streaming platform
# =============================================================================
# Layers:
#   * Base: official multi-arch flink:1.20-java11
#   * Python: system python3 + PyFlink 1.20 + job deps
#   * Plugins: flink-s3-fs-hadoop + flink-sql-connector-kafka +
#              flink-connector-jdbc + PostgreSQL JDBC driver
#   * Jobs: the ``jobs/`` package + Avro schemas (symlinked to
#           /opt/aqp-flink-jobs so FlinkSessionJob args can reference
#           /opt/aqp-flink-jobs/jobs/<name>.py via the operator uploader)
#
# Build with Buildx for multi-arch:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     -t ghcr.io/julianwiley/flink-trading:1.20 \
#     --push rpi_kubernetes/flink-jobs/
# =============================================================================
FROM flink:1.20-java11

USER root

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLINK_VERSION=1.20.3 \
    KAFKA_CONNECTOR_VERSION=3.2.0-1.20 \
    JDBC_CONNECTOR_VERSION=3.2.0-1.20 \
    POSTGRES_JDBC_VERSION=42.7.3

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        curl \
        ca-certificates \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Plugins -- each in its own subdirectory per the Flink plugin contract.
RUN mkdir -p /opt/flink/plugins/flink-s3-fs-hadoop \
             /opt/flink/plugins/flink-sql-connector-kafka \
             /opt/flink/plugins/flink-connector-jdbc \
    && cp /opt/flink/opt/flink-s3-fs-hadoop-${FLINK_VERSION}.jar \
          /opt/flink/plugins/flink-s3-fs-hadoop/ \
    && curl -fsSL -o /opt/flink/plugins/flink-sql-connector-kafka/flink-sql-connector-kafka-${KAFKA_CONNECTOR_VERSION}.jar \
          https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/${KAFKA_CONNECTOR_VERSION}/flink-sql-connector-kafka-${KAFKA_CONNECTOR_VERSION}.jar \
    && curl -fsSL -o /opt/flink/plugins/flink-connector-jdbc/flink-connector-jdbc-${JDBC_CONNECTOR_VERSION}.jar \
          https://repo1.maven.org/maven2/org/apache/flink/flink-connector-jdbc/${JDBC_CONNECTOR_VERSION}/flink-connector-jdbc-${JDBC_CONNECTOR_VERSION}.jar \
    && curl -fsSL -o /opt/flink/plugins/flink-connector-jdbc/postgresql-${POSTGRES_JDBC_VERSION}.jar \
          https://repo1.maven.org/maven2/org/postgresql/postgresql/${POSTGRES_JDBC_VERSION}/postgresql-${POSTGRES_JDBC_VERSION}.jar

# Install PyFlink and job dependencies.
COPY pyproject.toml /opt/aqp-flink-jobs/pyproject.toml
COPY jobs /opt/aqp-flink-jobs/jobs
RUN pip install --upgrade pip \
    && pip install \
        "apache-flink>=1.20,<1.21" \
        "fastavro>=1.9" \
        "numpy>=1.26" \
        "pandas>=2.1" \
        "requests>=2.31"

# PyFlink expects PYTHONPATH to include the job tree.
ENV PYTHONPATH=/opt/aqp-flink-jobs:${PYTHONPATH}

USER flink
