# aqp-agent-sandbox — gVisor RuntimeClass target

Phase 2 §5.1 scaffold for the agent-runtime sandbox. This image is
the deployment target for any pod that executes agent-generated code
(LLM-emitted strategies, multi-agent research bots, hash-locked
RL training jobs that touch user-provided code, …). The actual
runtime behavior lands in Phase 5 of
[RESTRUCTURING_PLAN.md](../../../../RESTRUCTURING_PLAN.md).

## Status

| Field | Value |
| --- | --- |
| Phase landed | 2 §5.1 (scaffold) |
| Phase activated | 5 §8 (per-tenant MCP + agent sandbox + biscuit caps) |
| Build matrix | NOT yet in `build-multi-arch.yml` — gated until Phase 5 wires it up |
| Pod-spec target | Will land in `aqp_platform/deployments/kubernetes/cells/<id>/agent-sandbox-pool/` (Phase 5) |
| RuntimeClass required | `gvisor` — enforced by Phase 2 §5.3 Kyverno policy `02-require-runtime-class.yaml` |

## Why this exists now

[RESTRUCTURING_PLAN.md §5.1](../../../../RESTRUCTURING_PLAN.md) lists
`aqp-agent-sandbox` as one of the three Phase 2 image names. The
Kyverno admission policy `02-require-runtime-class.yaml` (Phase 2
§5.3) needs to reference an actual image identifier — the scaffold
exists so the policy can target a real tag without depending on
Phase 5 deliverables.

## Build

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file aqp_platform/build/docker/aqp-agent-sandbox/Dockerfile \
  --tag ghcr.io/julianwiley/aqp-agent-sandbox:dev \
  .
```

## Smoke test

```bash
docker run --rm ghcr.io/julianwiley/aqp-agent-sandbox:dev &
# Expected (on stderr): "aqp-agent-sandbox: Phase 5 §8 placeholder"
# Container then sleeps forever; kill with `docker stop <id>`.
```

## What lands here in Phase 5

1. The real entry-point script in `aqp_platform_core.runtime.agent_sandbox`
   (Phase 5 §8.1).
2. Biscuit capability token validation
   ([§8.2](../../../../RESTRUCTURING_PLAN.md)) — every inbound request
   carries a biscuit token bound to the per-tenant MCP audience
   ([§8.5](../../../../RESTRUCTURING_PLAN.md)).
3. MCP tool descriptor-hash pinning
   ([§8.4](../../../../RESTRUCTURING_PLAN.md)) so a runtime drift in
   the tool registry can't silently expand the agent's authority.
4. Cell-bound audience claims for cross-cell calls
   ([§8.5](../../../../RESTRUCTURING_PLAN.md)).

## gVisor requirement

This image MUST be scheduled with `spec.runtimeClassName: gvisor`
([RESTRUCTURING_PLAN.md §8.3](../../../../RESTRUCTURING_PLAN.md)). The
Phase 2 §5.3 Kyverno policy
[`02-require-runtime-class.yaml`](../../../deployments/kubernetes/security/kyverno/cluster-policies/02-require-runtime-class.yaml)
denies admission to any Pod that pulls this image without the
matching RuntimeClass.

The RuntimeClass object itself lives at
`aqp_platform/deployments/kubernetes/cluster/gvisor-runtimeclass.yaml`
(Phase 5 §8.3) and is installed by
`aqp_platform/scripts/cluster_install/install-gvisor.sh` (Phase 5).
The Phase 2 deliverable is the *image name* and the *Kyverno policy
that enforces gvisor*; the RuntimeClass + the gVisor runtime
installation on each node are Phase 5 deliverables.
