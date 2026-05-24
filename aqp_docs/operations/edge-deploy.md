# Operations runbook — Edge deployment

Deploying AQP to edge / on-prem locations where the standard cloud K8s overlays don't fit.

## Reference shapes

### Shape A — single VM with Docker Compose

The simplest edge deployment: one Linux VM running the docker-compose stack with the admin overlay.

```bash
git clone https://github.com/julianwiley/agentic_quant_platform.git
cd agentic_quant_platform

# Generate config + bring up
make generate-config ENV=local
make dev-admin
```

Suitable for: dev labs, single-tenant trials, training environments.

Not suitable for: multi-node fault tolerance, HPA, NetworkPolicy enforcement.

### Shape B — k3s on a single edge box

For sites with a single VM but where you want production-style observability + Pod-level lifecycle:

```bash
curl -sfL https://get.k3s.io | sh -
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/dev
```

k3s ships with Traefik (substitute for the NGINX Ingress) and a built-in service load balancer (Klipper). You can install NGINX Ingress on top if you want to keep the same Ingress manifests as production.

### Shape C — rpi_kubernetes (4-node k3s lab)

The reference home/edge cluster shape per `rpi_kubernetes/README.md`:

- 4 Raspberry Pi 5 boards + 1 Ubuntu desktop running k3s
- Cloudflare Tunnel for the public edge
- MinIO + Postgres + Kafka + Flink + DataHub + MLflow as platform services

```bash
# In the rpi_kubernetes repo
kubectl apply -k kubernetes/                           # base platform
# Then in the agentic_quant_platform repo
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/dev   # AQP workloads
```

The AQP namespace + ConfigMap scaffold lands via [`kubernetes/base-services/aqp/`](../../../rpi_kubernetes/kubernetes/base-services/aqp/) (Phase 7 absorption).

## Edge-specific concerns

### Image distribution

Edge sites often have slow / metered uplinks. Mirror the AQP images into an on-site registry:

```bash
docker pull ghcr.io/julianwiley/aqp-client:latest-stable
docker tag ghcr.io/julianwiley/aqp-client:latest-stable mirror.local:5000/aqp-client:latest-stable
docker push mirror.local:5000/aqp-client:latest-stable
```

Then override the image tags in your overlay:

```yaml
# aqp_platform/deployments/kubernetes/overlays/edge-site-a/kustomization.yaml
images:
  - name: ghcr.io/julianwiley/aqp-client
    newName: mirror.local:5000/aqp-client
    newTag: latest-stable
```

### Auth0 unreachability

Edge sites may have intermittent connectivity to Auth0's JWKS endpoint. The JWT validator caches JWKS for `AQP_CP_AUTH_JWKS_TTL_SECONDS` (default 600s); set it higher (e.g. 3600s) so the cache spans typical outage windows.

In hard offline scenarios, set `AQP_AUTH_ENFORCE=permissive` so authenticated requests fall through to local-default identity and audit-log the violation. The operator UI shows a yellow banner when this mode is active.

### Storage

Edge sites should NOT rely on the in-cluster Postgres + Redis. Provision durable storage upstream and point AQP at it via the connectivity matrix:

```bash
AQP_DATABASE_URL=postgresql://aqp:****@cloud-postgres.example.com:5432/aqp
AQP_REDIS_URL=rediss://cloud-redis.example.com:6380
```

### Telemetry

Edge sites should forward telemetry to a central observability collector. Set `AQP_OTEL_COLLECTOR_URL` to the gateway endpoint; the control plane streams MetricPoints + AlertEvents to it via OTLP.

## Cutover from compose to k3s

If you started on shape A and want to move to shape B:

1. `docker compose down` to stop the compose stack.
2. Take a Postgres dump: `docker exec aqp-postgres pg_dump -U aqp aqp > aqp.sql`.
3. Bring up shape B per the recipe above.
4. Restore: `kubectl exec -n aqp deploy/aqp-postgres -- psql -U aqp aqp < aqp.sql`.
5. Verify `/manage/health` and `/health` both return 200.

No code changes required — the connectivity matrix abstracts which backend is hosting which service.
