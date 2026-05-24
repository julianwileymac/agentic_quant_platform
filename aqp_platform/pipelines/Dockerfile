FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/opt/app

WORKDIR /opt/app

COPY pipelines/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /tmp/requirements.txt

COPY pipelines /opt/app/pipelines

# Default entrypoint serves Dagster user code. Argo templates override command
# to run `python -m pipelines.cli ...` tasks.
CMD ["dagster", "api", "grpc", "-m", "pipelines.dagster_user_code.definitions", "-h", "0.0.0.0", "-p", "3030"]

