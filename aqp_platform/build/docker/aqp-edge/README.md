# aqp-edge — Envoy cell router image

Phase 2 §5.1 scaffold for the Envoy-based cell router. This directory
exists today only to reserve the build target and unblock parallel
Phase 3 work; the real cell-routing behavior lands in Phase 3 of
[RESTRUCTURING_PLAN.md](../../../../RESTRUCTURING_PLAN.md).

## Status

| Field | Value |
| --- | --- |
| Phase landed | 2 §5.1 (scaffold) |
| Phase activated | 3 §6.4 + Phase 5 §8.5 |
| Build matrix | NOT yet in `build-multi-arch.yml` — gated until Phase 3 wires it up |
| Pod-spec target | Will land in `aqp_platform/deployments/kubernetes/cells/<id>/aqp-edge/` (Phase 3) |
| Replaces | The Python FastAPI cell proxy (`aqp_client/` proxy module) per §6.6 |

## Why this exists now

[RESTRUCTURING_PLAN.md §5.1](../../../../RESTRUCTURING_PLAN.md) lists
`aqp-edge` as one of the three canonical Phase 2 image names alongside
`aqp-api` and `aqp-agent-sandbox`. Phase 3 (cell topology) starts on
week 6 — overlapping Phase 2 — and the §6.4 work needs the image name
already reserved so the Envoy operator manifests can target a real
tag during integration testing.

## Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file aqp_platform/build/docker/aqp-edge/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-edge:dev \
  .
```

The build context is the AQP repo root so the Dockerfile can `COPY` the
Phase-3 generated `envoy.yaml` from `aqp_platform/build/docker/aqp-edge/`.

## Smoke test

```bash
docker run --rm -p 10000:10000 ghcr.io/julianwiley/aqp-edge:dev &
curl -sS -o - http://127.0.0.1:10000/anything
# Expected: 503 with the "Phase 3 cell-router config has not been mounted yet" body.
```

## What lands here in Phase 3

1. A real `envoy.yaml` mounted via a Kubernetes ConfigMap; the
   placeholder `envoy.template.yaml` in this directory is the schema
   reference, not the runtime config.
2. The XDS cluster + listener feed from `/manage/cells/*`
   ([RESTRUCTURING_PLAN.md §6.4](../../../../RESTRUCTURING_PLAN.md)).
3. The `x-aqp-cell-id` header propagation contract from
   [§6.3](../../../../RESTRUCTURING_PLAN.md) (cell-aware
   `RequestContext`).
4. The `Cell-Bound-Authorization` (CBA) validator from
   [§8.5](../../../../RESTRUCTURING_PLAN.md) once biscuit capability
   tokens ship in §8.2.

## Why UID 65532 + Envoy distroless

Chainguard does not (yet) publish an Envoy image. Envoy upstream
ships its own distroless variant at `envoyproxy/envoy:distroless-*`
which runs as UID 101 (`envoy` user). The Phase 2 §5.4 PSS
convention is UID 65532; the Phase 2 §5.1 implementation pins to
`65532` explicitly in the `USER` directive, accepting the small
build cost of `chown`'ing a writable working directory once. This
is the single documented exception to the "use the upstream image
default UID" rule for AQP-owned images, captured in
[`aqp_platform/deployments/kubernetes/security/README.md`](../../../deployments/kubernetes/security/README.md).
