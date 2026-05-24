# =============================================================================
# RPi Kubernetes Management API - Dockerfile
# =============================================================================
# Multi-stage build for optimal image size.
# Build context must be the REPO ROOT so the Alpha Vantage client library can be
# copied. See bootstrap/scripts/build-management.sh which runs:
#     docker build -f management/backend/Dockerfile -t rpi-k8s-management:latest .
# from the repo root.
# =============================================================================

FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY management/backend/pyproject.toml management/backend/README.md ./
# The AV client library is bundled from integrations/alphavantage.
COPY integrations/alphavantage /opt/alphavantage-client
RUN pip install --no-cache-dir hatch && \
    pip install --no-cache-dir . && \
    pip install --no-cache-dir /opt/alphavantage-client

# =============================================================================
# Production image
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY management/backend/src/ ./src/

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8080

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/live || exit 1

# Run application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
