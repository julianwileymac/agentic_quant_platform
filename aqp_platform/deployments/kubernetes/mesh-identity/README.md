# Mesh + identity tree (Phase 4)

Phase 4 of [RESTRUCTURING_PLAN.md](../../../../RESTRUCTURING_PLAN.md).
Per-cell installs of the service mesh, workload-identity, identity-
aware proxy, and projected-secret operator components.

## Layout

```
mesh-identity/
  linkerd/                  # §7.1 Linkerd 2.16 control plane
  spire/                    # §7.2 SPIRE Server + Agent
  pomerium/                 # §7.5 Pomerium IAP
  vault-secrets-operator/   # §7.6 VSO operator + sample CRs
```

Each subdirectory is a kustomize base that a per-cell overlay at
`aqp_platform/deployments/kubernetes/cells/<cell-id>/<component>/`
references. The Argo CD `cells` `ApplicationSet`
([applicationsets/cells-appset.yaml](../../argocd/applicationsets/cells-appset.yaml))
will be extended in Phase 4.5 to stamp one component-Application per
cell × component pair, so each cell ends up with its own Linkerd /
SPIRE / Pomerium / VSO control plane.

## Phase 4 status

| Component | What ships in Phase 4 | What Phase 4.5 finishes |
| --- | --- | --- |
| Linkerd 2.16 | Helm-based install manifest + sample namespace injection annotation pattern | Per-cell overlay wiring + golden-signal dashboards in linkerd-viz |
| SPIRE 1.10 | StatefulSet + DaemonSet + CRD bindings + trust-domain config | Per-cell SVID issuance policies + Workload Attestor selectors |
| Pomerium IAP | Operator install + route template for `/manage/*` | Per-cell route CRDs + step-up MFA wiring |
| vault-secrets-operator | Operator install + sample `VaultStaticSecret` for cell Postgres | Per-cell `VaultStaticSecret` set for every persistent service |

## Apply

The shared templates work with `kubectl apply -k` per component:

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/linkerd/
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/spire/
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/pomerium/
kubectl apply -k aqp_platform/deployments/kubernetes/mesh-identity/vault-secrets-operator/
```

In production the apply is driven by Argo CD; manual `kubectl apply`
is the smoke-test path documented in
[../../../../aqp_docs/docs/how-to/linkerd-spire-rollout.md](../../../../aqp_docs/docs/how-to/linkerd-spire-rollout.md).

## Why per-cell, not cluster-wide

The plan §7.1 explicitly calls out cluster-wide mesh installs as an
anti-pattern for the cell model. One Linkerd control plane per cell
gives:

- **Isolation domain alignment**: cell = isolation boundary; mesh
  scope = cell. Cross-cell calls go through `aqp-edge` (Envoy) so
  mTLS terminates and re-terminates at the cell boundary — by
  design, not by accident.
- **Blast-radius containment**: a control-plane upgrade affects one
  cell at a time.
- **SPIFFE trust-domain alignment**: each cell can carry its own
  trust domain suffix (`spiffe://aqp.fund/cell/<cell-id>/...`) so
  cross-cell SVID validation is explicit, never implicit.

Cluster-wide installs are reserved for: Kyverno (Phase 2 §5.3),
gVisor RuntimeClass (Phase 5 §8.3), node-local DNS, kube-proxy.
