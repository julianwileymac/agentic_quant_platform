# aqp-index debt — Phase 2 container & supply-chain hardening

> Per the always-on
> [aqp-index-reflect rule](../rules/aqp-index-reflect.mdc), Phase 2
> §5 of
> [RESTRUCTURING_PLAN.md](../../RESTRUCTURING_PLAN.md) touches enough
> qualifying surfaces that `aqp_index/` MUST be refreshed by the
> [`aqp-index-curator`](../agents/aqp-index-curator.md) subagent in the
> same PR — OR a debt note (this file) must capture the changed
> surfaces so the curator's next scheduled pass picks them up.
>
> This note is option 2. Invoke the curator before merging if at all
> possible.

## Surfaces changed in Phase 2

### `aqp_platform/`

- **`aqp_platform/Dockerfile`** — master Dockerfile rebased on
  `cgr.dev/chainguard/python:3.11-dev`; every install step swapped
  from `pip install -e` to `uv pip install --system -e`. All five
  final stages now `USER 65532:65532` (was UID 1001 / root mixed).
  Each final stage's `CMD` is now preceded by `ENTRYPOINT []` because
  Chainguard's Python runtime image defaults `ENTRYPOINT` to
  `/usr/bin/python`.
- **`aqp_platform/build/docker/aqp_control_plane/Dockerfile`** —
  rewritten as multi-stage (Chainguard `3.11-dev` builder + `3.11`
  runtime). Venv-based install at `/opt/aqp-cp-venv/`. Runs as UID
  65532 (was UID 1000).
- **`aqp_platform/build/docker/aqp_client/Dockerfile`** — three
  stages → four (added `production-builder`). Chainguard Node 20-dev
  + Chainguard Python 3.11-dev (builders) + Chainguard Python 3.11
  (runtime). Drops `tini` ENTRYPOINT (Kubernetes handles PID 1
  signal forwarding). Runs as UID 65532 (was UID 1000).
- **`aqp_platform/build/docker/aqp_ui/Dockerfile`** — both stages on
  Chainguard Node 20. Drops `libc6-compat` shim (Chainguard is
  glibc, not musl). Runs as UID 65532.
- **`aqp_platform/build/docker/aqp-edge/`** (NEW) — Phase 2 §5.1
  scaffold for the Envoy cell router image. Dockerfile + envoy
  placeholder + README. Activation deferred to Phase 3 §6.4.
- **`aqp_platform/build/docker/aqp-agent-sandbox/`** (NEW) —
  Phase 2 §5.1 scaffold for the gVisor RuntimeClass target image.
  Dockerfile + README. Activation deferred to Phase 5 §8.
- **`aqp_platform/deployments/kubernetes/security/`** (NEW
  top-level overlay) — six Kyverno `ClusterPolicy` objects in
  Audit mode, with kustomizations + a comprehensive README that
  enumerates the per-namespace PSS exception list, the
  `hostNetwork` exception list, the UID 65532 exception list,
  and the Phase 2.5 Audit → Enforce ratchet plan.
- **`aqp_platform/deployments/kubernetes/base/namespace.yaml`** —
  added `aqp.io/component`, FinOps quartet (`project`,
  `cost_center`, `owner`, `data_classification`), PSS version
  pins (`enforce-version: latest`, etc.) to the `aqp` and
  `aqp-admin` namespaces.
- **`aqp_platform/deployments/kubernetes/base/namespaces-shared.yaml`**
  — backfilled `aqp.io/component` + `aqp.io/pss-exception` +
  PSS version pins + FinOps quartet on the 9 shared namespaces
  (streaming, timeseries, lakehouse, observability, data-services,
  mlops, elt, edge, bots). Added `aqp.io/host-network-allowed:
  "true"` to `aqp-edge` so the `03-no-host-network` Kyverno
  policy doesn't fire on cloudflared.
- **`aqp_platform/deployments/kubernetes/base/aqp-ui/namespace.yaml`**
  — added PSS labels (was FinOps-only), `aqp.io/component`,
  version pins.
- **`aqp_platform/deployments/kubernetes/aqp-ide/namespace.yaml`** —
  added `aqp.io/component`, `aqp.io/pss-exception`, audit label,
  version pins, FinOps quartet.

### `aqp_bots/`

- **`aqp_bots/Dockerfile`** + **`aqp_bots/Dockerfile.hft`** — header
  comment block added explaining the documented Phase 2 §5.1
  exemption from Chainguard migration (distroless nonroot for the
  standard runtime, Debian-slim for HFT kernel-bypass libs).
  Bodies unchanged.

### `.github/workflows/`

- **`.github/workflows/build-multi-arch.yml`** — added
  `id-token: write` + `packages: write` + `attestations: write`
  permissions; added `workflow_dispatch.inputs.rollback`
  policy-anchor input; per-image cosign + syft + grype steps
  (mirrors the proven `quantbot-bots-image.yml` pattern but uses
  CycloneDX SBOM and grype scan); upgraded the `inspect` job with
  `cosign verify` + `cosign verify-attestation` post-checks.

### `aqp_docs/`

- **`aqp_docs/docs/how-to/chainguard-base-migration.md`** (NEW) —
  Phase 2 runbook covering the Chainguard rationale, per-image
  scope, local verification of cosign + SBOM + grype, the
  Audit → Enforce ratchet workflow, and the rollback path.

## Files the curator should refresh

The qualifying surfaces above map to these `aqp_index/` files (per
the curator's scan plan):

| `aqp_index/` file | Why it needs a refresh |
| --- | --- |
| `aqp_index/projects/aqp_platform.md` | Dockerfile inventory; security/ overlay is new; aqp-edge + aqp-agent-sandbox image scaffolds are new |
| `aqp_index/projects/aqp_bots.md` | Dockerfile header changed (exemption note) |
| `aqp_index/projects/aqp_docs.md` | New runbook at how-to/chainguard-base-migration.md |
| `aqp_index/sources-of-truth.md` | Container supply chain is now in scope; cosign keyless + Rekor are new SSoT pointers |
| `aqp_index/config-sets/k8s-overlays.md` | New `security/` overlay; new `aqp.io/component` + `aqp.io/pss-exception` namespace labels |
| `aqp_index/config-sets/ci-workflows.md` | `build-multi-arch.yml` permissions + cosign + SBOM + grype jobs |

## Phase 2 sub-section coverage

| RESTRUCTURING_PLAN.md sub-§ | Status |
| --- | --- |
| §5.1 Chainguard Wolfi base migration | Complete on 4 platform Dockerfiles; aqp_bots is a documented exemption |
| §5.2 Cosign keyless + SBOM attestation | Complete on `build-multi-arch.yml` (api, worker, client) |
| §5.3 Kyverno cluster policies | Complete in Audit mode; ratchet plan in security/README.md |
| §5.4 Pod Security Standards (restricted) | Complete on all AQP-owned namespaces; exception list documented |
| §5.5 Outdated rollback artifacts | Complete — `workflow_dispatch.inputs.rollback` gate added with policy anchor comment |
| §5.6 Phase 2 deliverables table | All eight rows mapped to landed files (see this debt note) |

## Follow-ups (Phase 2.5)

These are NOT part of this PR — listed so the curator can flag them
on the next refresh:

1. **uv.lock generation**. `aqp_platform/Dockerfile` uses
   `uv pip install --system -e` (uv's pip-compatible interface) which
   does not require a lock file. The strict
   `uv sync --frozen` pattern recommended at RESTRUCTURING_PLAN.md
   §5.1 requires a committed `uv.lock` at the repo root. Future PR
   to generate + commit.
2. **install-kyverno.sh**. The Phase 2.5 cluster-install script
   that installs the Kyverno admission webhook. Lives at
   `aqp_platform/scripts/cluster_install/install-kyverno.sh`
   (not yet created).
3. **Audit → Enforce ratchet**. Per the table in
   `aqp_platform/deployments/kubernetes/security/README.md`, six
   Kyverno policies move from Audit to Enforce in Phase 2.5 once
   the 7-day zero-violation soak completes.
4. **Multi-arch Trivy scan in security-scan.yml**. The existing
   `security-scan.yml` builds `linux/amd64` only; should bump to
   the multi-arch matrix to catch arch-specific CVEs.
5. **Per-cell Kyverno policies (Phase 3+)**. Once the cell-router
   topology lands, the cluster policies become cell-scoped via
   `policySetSelector`.

## Provenance

- Discovered while implementing
  [RESTRUCTURING_PLAN.md](../../RESTRUCTURING_PLAN.md) Phase 2 in
  the same PR.
- All surfaces enumerated above show up in `git status` for this
  PR; the curator can scan that diff directly.
