# =============================================================================
# aqp-agent-sandbox — gVisor RuntimeClass target for agent-generated code.
#
# Phase 2 §5.1 (RESTRUCTURING_PLAN.md) scaffold. The actual sandbox
# behavior + per-tenant MCP isolation + biscuit capability tokens are
# all Phase 5 work (RESTRUCTURING_PLAN.md §8 — Per-tenant MCP & agent
# sandbox). This image exists today to reserve the name and unblock
# parallel Phase 5 work.
#
# Pod spec MUST set ``spec.runtimeClassName: gvisor`` and apply the
# matching Kyverno policy from
# ``aqp_platform/deployments/kubernetes/security/kyverno/cluster-policies/
#  02-require-runtime-class.yaml`` (Phase 2 §5.3).
#
# Build:
#   docker buildx build \
#     --platform linux/amd64,linux/arm64 \
#     --file aqp_platform/build/docker/aqp-agent-sandbox/Dockerfile \
#     --tag ghcr.io/julianwiley/aqp-agent-sandbox:dev \
#     .
# Build context is the AQP repo root so we can COPY from aqp/, aqp_platform_core/.
# =============================================================================
ARG BUILDPLATFORM
ARG TARGETPLATFORM

# -----------------------------------------------------------------------------
# Stage 1 — builder (Chainguard Python 3.11-dev + uv).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11-dev AS builder

WORKDIR /app
USER root

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

RUN apk add --no-cache build-base curl

COPY --from=ghcr.io/astral-sh/uv:0.6.0 /uv /usr/local/bin/uv

COPY aqp_platform_core /app/aqp_platform_core
COPY pyproject.toml /app/pyproject.toml

# Phase 2 scaffold install set: just the minimum the agent runtime
# entry point needs. Phase 5 §8.1 will expand this to the per-tenant
# MCP client surface + biscuit capability validation, but those edges
# do not yet exist.
RUN python -m venv /opt/aqp-agent-sandbox-venv \
 && /opt/aqp-agent-sandbox-venv/bin/uv pip install \
        --python /opt/aqp-agent-sandbox-venv/bin/python \
        -e /app/aqp_platform_core \
 && /opt/aqp-agent-sandbox-venv/bin/uv pip install \
        --python /opt/aqp-agent-sandbox-venv/bin/python \
        "httpx>=0.27,<1" \
        "pydantic>=2.6,<3" \
        "structlog>=24.1,<25"

# -----------------------------------------------------------------------------
# Stage 2 — runtime (Chainguard Python 3.11, nonroot UID 65532).
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM cgr.dev/chainguard/python:3.11 AS runtime

LABEL org.opencontainers.image.title="aqp-agent-sandbox" \
      org.opencontainers.image.description="AQP agent runtime sandbox (gVisor RuntimeClass target) - Phase 5 §8 stub" \
      org.opencontainers.image.source="https://github.com/julianwiley/agentic_quant_platform" \
      org.opencontainers.image.licenses="Proprietary"

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/aqp-agent-sandbox-venv/bin:$PATH \
    AQP_AGENT_SANDBOX=true

COPY --from=builder /opt/aqp-agent-sandbox-venv /opt/aqp-agent-sandbox-venv
COPY --from=builder /app/aqp_platform_core /app/aqp_platform_core

# Phase 2 scaffold: print a hello-world line + sleep forever so the
# Pod's livenessProbe (kubelet exec) can confirm the binary works
# without the agent runtime existing yet. Phase 5 will replace this
# with the actual ``aqp_agent_runtime`` console script.
USER 65532:65532

ENTRYPOINT ["/opt/aqp-agent-sandbox-venv/bin/python"]
CMD ["-c", "import time, sys; print('aqp-agent-sandbox: Phase 5 §8 placeholder', file=sys.stderr); time.sleep(2_147_483_647)"]
