# /deployments/ — runtime artifacts

Owns the docker-compose files and Kubernetes manifests for every supported AQP deployment shape.

## Structure

```
deployments/
├── compose/
│   ├── docker-compose.base.yml          # Shared service definitions (networks, volumes)
│   ├── docker-compose.local.yml         # Full local dev stack
│   ├── docker-compose.override.yml      # Developer-local overrides (ports, mounts)
│   ├── docker-compose.legacy.yml        # Solara profile + legacy webui rollback
│   ├── docker-compose.admin.yml         # aqp_client + aqp_control_plane together
│   ├── .env.schema                       # Source of truth for env variables
│   ├── .env.local.template               # Generated local template
│   └── .env.cloud.template               # Generated cloud / K8s template
└── kubernetes/
    ├── base/                              # Plain Kubernetes manifests
    │   ├── namespace.yaml
    │   ├── network-policies.yaml
    │   ├── rbac/
    │   ├── configmaps/
    │   ├── secrets/
    │   ├── aqp-client/, aqp-core/, aqp-worker/, aqp-cp/, redis-master/
    │   └── ingress.yaml
    ├── overlays/
    │   ├── dev/                           # Kustomize dev overlay
    │   ├── staging/
    │   └── prod/
    └── helm/
        ├── aqp-backend/
        ├── aqp-redis/
        ├── aqp-workers/
        └── aqp-control-plane/
```

## Ownership

- `compose/` — Platform team (developer experience + admin overlay)
- `kubernetes/base/` — Platform team (canonical manifests)
- `kubernetes/overlays/` — Each env's owner (dev = platform; staging + prod = SRE)
- `kubernetes/helm/` — Platform team (Helm charts for external consumers / mirroring)

## Invariants

- The `.env.schema` is the single source of truth. Every variable declared anywhere (compose, K8s ConfigMap, K8s Secret, application code) MUST appear in the schema.
- Compose: `docker compose -f deployments/compose/docker-compose.base.yml -f docker-compose.local.yml --env-file deployments/compose/.env.local up`
- K8s: `kubectl apply -k deployments/kubernetes/overlays/<env>`
- Helm charts mirror the K8s base for external consumers (when the AQP install is part of a larger cluster, not the only thing in it).

## Related

- Generation utility: [`build/scripts/generate_config.py`](../build/scripts/generate_config.py)
- Makefile entry points: `make dev`, `make dev-client`, `make dev-admin`, `make generate-config ENV=...`
- Existing Terraform-driven deploy: `aqp deploy up` (canonical for local k3d; cf. ADR 005)
