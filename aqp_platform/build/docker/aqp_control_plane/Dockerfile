# AQP control plane sidecar image (aqp_control_plane + aqp_platform_core only).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY aqp_platform_core ./aqp_platform_core
COPY aqp_control_plane ./aqp_control_plane

RUN pip install --upgrade pip \
    && pip install -e ./aqp_platform_core \
    && pip install -e "./aqp_control_plane[kubernetes]"

RUN useradd --system --uid 1000 --create-home aqp
USER aqp

EXPOSE 9000
CMD ["uvicorn", "aqp_cp.main:app", "--host", "0.0.0.0", "--port", "9000"]
