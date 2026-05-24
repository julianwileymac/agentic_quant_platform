# aqp-control-plane

Isolated FastAPI micro-project for AQP runtime workload operations.

This is the implementation of AGENTS hard rule 45 + ADR 005:

- All workload runtime ops (start / stop / scale / restart / exec / logs /
  `apply_config`) go through the `InfrastructureProvider` ABC
- Five providers: `docker_compose`, `kubernetes`, `aws` (EKS + ECS Fargate),
  `azure` (AKS + ACI), `gcp` (GKE + Cloud Run)
- JWT-validated `/manage/*` REST API + telemetry WebSocket
- Standalone — depends on `aqp-platform-core` only, NEVER imports `aqp.*`

## Structure

```
aqp_control_plane/
├── pyproject.toml            # Own packaging
├── Dockerfile                # Standalone build
├── src/
│   └── aqp_cp/
│       ├── main.py           # FastAPI app entrypoint
│       ├── settings.py       # pydantic-settings BaseSettings
│       ├── auth/             # JWT validator + RBAC + resource filter
│       │   ├── validator.py
│       │   ├── deps.py       # FastAPI Depends: require_auth, require_scope
│       │   └── rbac.py
│       ├── models/           # Re-exports + control-plane-specific Pydantic models
│       │   ├── deployment.py
│       │   ├── telemetry.py
│       │   └── audit.py      # WorkloadRun ledger row schema
│       ├── providers/        # Five InfrastructureProvider impls (Phase 5 fan-out)
│       │   ├── docker_compose.py
│       │   ├── kubernetes.py
│       │   ├── aws.py
│       │   ├── azure.py
│       │   └── gcp.py
│       ├── api/
│       │   ├── routers/
│       │   │   ├── deployments.py
│       │   │   ├── telemetry.py
│       │   │   ├── config.py
│       │   │   ├── secrets.py
│       │   │   └── health.py
│       │   └── errors.py
│       └── services/
│           ├── lifecycle.py  # Orchestrates provider.start/stop/scale
│           ├── telemetry.py  # 10s polling + alert forwarding
│           └── audit.py      # WorkloadRun ledger writer
└── tests/
    ├── auth/
    ├── api/
    └── providers/            # Contract tests (mocked SDKs)
```

## Install + run (local)

```bash
# From the monorepo root
pip install -e ./aqp_platform_core
pip install -e ./aqp_control_plane[dev,all-providers]

# Bring up against the local docker-compose stack
AQP_CP_PROVIDER=docker_compose \
AQP_CP_COMPOSE_FILE=$(pwd)/deployments/compose/docker-compose.local.yml \
uvicorn aqp_cp.main:app --host 0.0.0.0 --port 9000
```

## Run in a container

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file aqp_platform/build/docker/aqp_control_plane/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-control-plane:dev \
  .

docker run --rm -p 9000:9000 \
  -e AQP_CP_PROVIDER=kubernetes \
  -v ~/.kube/config:/home/aqp/.kube/config:ro \
  ghcr.io/julianwiley/aqp-control-plane:dev
```

Health check: `curl http://localhost:9000/manage/health` returns 200.

## Strict isolation invariant

```bash
# CI lint that runs on every PR (.github/workflows/ci.yml)
rg --type python "^from aqp(\.|$)|^import aqp(\.|$)" aqp_control_plane/src/ \
  && echo "FAIL: aqp_control_plane imports forbidden aqp.* module" && exit 1
```
