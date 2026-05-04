FROM apache/superset:4.1.1

USER root

# psycopg2-binary is required because the Compose stack points
# SUPERSET__SQLALCHEMY_DATABASE_URI at postgresql+psycopg2://; sqlalchemy-trino
# powers the curated ``AQP Trino Iceberg`` database we provision via the sync
# task; redis is used by every Superset cache config in superset_config.py.
RUN pip install --no-cache-dir \
    psycopg2-binary \
    sqlalchemy-trino \
    redis

COPY bootstrap.sh /app/bootstrap.sh
# Normalise Windows CRLF line endings before chmod so the shebang resolves
# correctly inside the container (otherwise: ``/usr/bin/env: 'bash\r'``).
RUN sed -i 's/\r$//' /app/bootstrap.sh && chmod +x /app/bootstrap.sh

USER superset
