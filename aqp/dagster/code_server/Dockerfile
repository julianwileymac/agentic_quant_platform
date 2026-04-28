# AQP Dagster code-location image.
#
# Mirrors the cluster's pipelines-user-code base
# (dagster/dagster-celery-k8s:1.12.21) so the gRPC API contract matches.
# Loads the AQP package + the data-fabric extras (Iceberg, Dask, Ray,
# DataHub) and starts a gRPC server pointing at
# `aqp.dagster.definitions`.
FROM dagster/dagster-celery-k8s:1.12.21

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AQP_DAGSTER_MODULE_PATH=aqp.dagster.definitions \
    AQP_DAGSTER_CODE_LOCATION=aqp \
    AQP_DAGSTER_GRPC_HOST=0.0.0.0 \
    AQP_DAGSTER_GRPC_PORT=4000

WORKDIR /opt/aqp

# Source. In CI the build context is the repo root; this layer
# contains the agentic_quant_platform Python package.
COPY pyproject.toml README.md ./
COPY aqp ./aqp
COPY alembic ./alembic
COPY configs ./configs
COPY scripts ./scripts

# Install the package + the data-fabric extras. ``--no-deps`` would
# clip the runtime requirements; instead rely on the project's own
# pinned dependency set.
RUN pip install --upgrade pip && \
    pip install ".[data-fabric]"

# Copy the entrypoint last so iterative changes don't bust the install layer.
COPY aqp/dagster/code_server/entrypoint.sh /opt/aqp/entrypoint.sh
RUN chmod +x /opt/aqp/entrypoint.sh

EXPOSE 4000
ENTRYPOINT ["/opt/aqp/entrypoint.sh"]
