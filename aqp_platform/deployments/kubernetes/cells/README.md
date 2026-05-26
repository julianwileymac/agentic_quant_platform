# Per-cell K8s overlays (Phase 3 §6.5)

Phase 3 §6.5 of [RESTRUCTURING_PLAN.md](../../../../RESTRUCTURING_PLAN.md)
— per-cell Kubernetes manifest overlays. Each cell in the registry
maps to one overlay here; the cell's Argo CD `Application` (stamped
by the `ApplicationSet` at
`../../../argocd/applicationsets/cells-appset.yaml`) renders the
overlay and applies the result to the cell's namespace.

## Layout

```
cells/
  shared-std-us-east-1a/       # Phase 3 worked example
  shared-prem-us-east-1a/      # Phase 3 worked example
  silo-reg-acme/               # Phase 3 worked example (Acme tenant)
  <future cell-id>/
```

Each overlay:

1. References `../../base` for the canonical workload set
   (aqp-core, aqp-worker, aqp-client, aqp-cp, redis-master).
2. Pins the cell's `k8s_namespace` from the cells registry.
3. Stamps `aqp.io/cell-id`, `aqp.io/cell-tier`,
   `aqp.io/cell-region`, `aqp.io/tenancy-strategy` on every
   workload + the namespace.
4. Overrides the per-cell replica counts (tier-dependent).
5. (Phase 6 §9.1) Will pin per-cell Postgres + MinIO + MLflow
   service names.

## Local apply (no Argo CD)

Cell overlays import `../../base-cell` which lists files from the
sibling `../base/` tree. Kustomize's default load-restrictor
forbids cross-directory file references, so cell builds REQUIRE
the `--load-restrictor=LoadRestrictionsNone` flag:

```bash
# Verify a cell overlay builds:
kubectl kustomize --load-restrictor=LoadRestrictionsNone   aqp_platform/deployments/kubernetes/cells/shared-std-us-east-1a/

# Apply (only when the cell namespace already exists):
kubectl apply -k --load-restrictor=LoadRestrictionsNone   aqp_platform/deployments/kubernetes/cells/shared-std-us-east-1a/
```

Argo CD's `ApplicationSet` at
`../../argocd/applicationsets/cells-appset.yaml` sets the same flag
via `spec.source.kustomize.commonOptions` so cluster syncs Just Work.

## Rolling out a new cell

1. Add the cell to `aqp_platform/configs/deployment/topology.yaml`
   under `cells:` (Phase 3 §6.2 — bootstrap seed).
2. Insert a row into the `cells` table via
   `POST /manage/cells` (Phase 3 §6.2 — control-plane router).
3. Add an overlay directory here using one of the existing ones as
   a template.
4. Argo CD `ApplicationSet` (Phase 3 §6.5) picks up the new
   overlay on the next sync. The cell rolls out via the standard
   Argo CD progressive sync.
5. Flip the cell's `state` from `provisioning` to `active` via
   `PATCH /manage/cells/{cell_id}/state`.

## Phase 6 §9.1 follow-up

The current overlays still use the shared `aqp` namespace's
Postgres + Redis + MinIO. Phase 6 §9.1 swaps these for per-cell
CNPG + Redis + MinIO instances; the overlay tree will grow a
matching set of per-cell datastore manifests at that point.
