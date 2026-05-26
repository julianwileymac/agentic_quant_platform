---
title: Chainguard base migration runbook
description: Phase 2 §5.1 runbook — migrate AQP Dockerfiles to cgr.dev/chainguard/* bases, verify cosign keyless signatures + SBOMs, ratchet Kyverno from Audit to Enforce.
sidebar_label: Chainguard base migration
---

# Chainguard base migration runbook

> Phase 2 §5.1 + §5.2 + §5.3 + §5.4 of
> [RESTRUCTURING_PLAN.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md).
> Owns the cutover from Debian-slim base images to Chainguard Wolfi
> bases, the cosign + SBOM signing pipeline, and the Kyverno
> admission policies that gate signed-only images in production.

## Scope

Four AQP-owned images move to Chainguard Wolfi in Phase 2 §5.1:

| Image | Dockerfile | Base before | Base after |
| --- | --- | --- | --- |
| `aqp-api` / `aqp-worker` (shared `api` target) | `aqp_platform/Dockerfile` | `python:3.11-slim` | `cgr.dev/chainguard/python:3.11-dev` |
| `aqp-control-plane` | `aqp_platform/build/docker/aqp_control_plane/Dockerfile` | `python:3.11-slim` | `cgr.dev/chainguard/python:3.11-dev` (builder) + `cgr.dev/chainguard/python:3.11` (runtime) |
| `aqp-client` | `aqp_platform/build/docker/aqp_client/Dockerfile` | `node:20-alpine` + `python:3.11-slim` | `cgr.dev/chainguard/node:20-dev` + `cgr.dev/chainguard/python:3.11-dev` (builders) + `cgr.dev/chainguard/python:3.11` (runtime) |
| `aqp-ui` | `aqp_platform/build/docker/aqp_ui/Dockerfile` | `node:20-alpine` | `cgr.dev/chainguard/node:20-dev` (builder) + `cgr.dev/chainguard/node:20` (runtime) |

Two images carry **documented exemptions** and stay on their current
bases:

| Image | Dockerfile | Reason |
| --- | --- | --- |
| `aqp-bots` standard | `aqp_bots/Dockerfile` | Already on `gcr.io/distroless/python3-debian12:nonroot` — smaller and more locked-down than Chainguard Python, no shell at all. Builder stage stays on `python:3.12-slim-bookworm` for build-essential availability. |
| `aqp-bots` HFT | `aqp_bots/Dockerfile.hft` | Kernel-bypass libs (DPDK, Onload, Mellanox OFED) require kernel headers + `libnuma1` + `linuxptp` + `ethtool` + `kmod` which Chainguard's nonroot Wolfi runtime image does not ship. Per ADR 007. |

Two **future-phase scaffolds** are created in Phase 2 §5.6:

| Image | Dockerfile | Activation phase |
| --- | --- | --- |
| `aqp-edge` (Envoy cell router) | `aqp_platform/build/docker/aqp-edge/Dockerfile` | Phase 3 §6.4 (cell topology) |
| `aqp-agent-sandbox` (gVisor target) | `aqp_platform/build/docker/aqp-agent-sandbox/Dockerfile` | Phase 5 §8 (per-tenant MCP + agent sandbox) |

## Why Chainguard Wolfi

- **glibc**, not musl — keeps native wheel compatibility for
  `numpy`, `pyarrow`, `torch`, `psycopg2`, etc. The
  RESTRUCTURING_PLAN footnote at §5.1 explicitly notes that
  Alpine/musl-style minimalism breaks the native-wheel toolchain.
- **Continuously rebuilt** — Chainguard ships a fresh image set
  every ~24 hours, so CVE patches land without us doing anything
  beyond a rebuild. Pair with Renovate (Phase 1 §4.7) to
  re-trigger the build matrix on a base-image bump.
- **No CVEs in the base** — Chainguard runs distroless-style
  scans and publishes a daily-zero-CVE SLO for `latest` tags. We
  still run `grype --fail-on high` per Phase 2 §5.2 because
  application-level CVEs are our responsibility.
- **Single nonroot UID convention (65532)** — matches the Phase 2
  §5.4 PSS restricted profile. The runtime stages never run as
  root; the `-dev` builder runs as root only for `apk add`.

## Build verification

Local one-off build (no push, no signing — for inner-loop dev):

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --target api \
  --file aqp_platform/Dockerfile \
  --tag aqp-api:dev \
  .
```

Multi-arch build via `build-multi-arch.yml` (CI canonical path):

```bash
gh workflow run build-multi-arch.yml \
  --ref feat/phase-2-supply-chain
```

The workflow signs every pushed image with cosign keyless OIDC
and uploads a CycloneDX SBOM. The `inspect` job at the bottom of
the workflow runs `cosign verify` + `cosign verify-attestation`
to confirm the signature + SBOM attestation land in Rekor.

### Verify cosign signature locally

```bash
cosign verify \
  --certificate-identity-regexp 'https://github.com/julianwiley/agentic_quant_platform/.github/workflows/build-multi-arch\.yml@refs/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  docker.io/julianwiley/aqp-api:latest
```

Expected exit code: 0. The output prints the signature payload
including the Rekor transparency log entry index.

### Verify CycloneDX SBOM attestation locally

```bash
cosign verify-attestation \
  --certificate-identity-regexp 'https://github.com/julianwiley/agentic_quant_platform/.github/workflows/build-multi-arch\.yml@refs/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --type cyclonedx \
  docker.io/julianwiley/aqp-api:latest > sbom-attestation.json
```

The `predicate` field of the attestation is the base64-encoded
CycloneDX document.

### Re-run grype against the SBOM

```bash
syft docker.io/julianwiley/aqp-api:latest -o cyclonedx-json=sbom.json
grype sbom:sbom.json --fail-on high
```

Exit code 0 = no HIGH or CRITICAL CVEs; non-zero = the gate fires
in CI.

## Kyverno audit-to-enforce ratchet

The six Phase 2 §5.3 cluster policies ship in `Audit` mode (see
[aqp_platform/deployments/kubernetes/security/README.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp_platform/deployments/kubernetes/security/README.md)).
The ratchet schedule:

| Policy | Audit-mode soak | Enforce gate |
| --- | --- | --- |
| `00-verify-signatures.yaml` | 7 days zero violations across all AQP-owned namespaces | Phase 2.5 |
| `01-require-pss-restricted.yaml` | 7 days zero violations | Phase 2.5 |
| `02-require-runtime-class.yaml` | DO NOT enforce until Phase 5 §8.3 lands the gVisor RuntimeClass | Phase 5.1 |
| `03-no-host-network.yaml` | 7 days zero violations after `aqp-edge` namespace carries `aqp.io/host-network-allowed: "true"` | Phase 2.5 |
| `04-no-privilege-escalation.yaml` | 7 days zero violations | Phase 2.5 |
| `05-required-labels.yaml` | 7 days zero violations on namespaces that carry `aqp.io/component` | Phase 2.5 |

### Operator workflow to flip Audit → Enforce

```bash
# 1. Verify zero violations for the target policy:
kubectl get clusterpolicyreport -o jsonpath='{range .items[*].results[?(@.policy=="aqp-verify-image-signatures")]}{.result}{"\n"}{end}' \
  | sort | uniq -c

# Expected output: only "pass" lines. Any "fail" lines block the ratchet.

# 2. Patch the policy in place:
kubectl patch clusterpolicy aqp-verify-image-signatures \
  --type=merge \
  -p '{"spec":{"validationFailureAction":"Enforce"}}'

# 3. Update the YAML in tree so the audit-only state is preserved:
sed -i 's/validationFailureAction: Audit/validationFailureAction: Enforce/' \
  aqp_platform/deployments/kubernetes/security/kyverno/cluster-policies/00-verify-signatures.yaml

# 4. Commit + open PR with `[Phase 2.5 ratchet]` in the title.
```

## Rollback

The Chainguard migration is reversible per Dockerfile. Each
Dockerfile carries a `Phase 2 §5.1` comment at the top documenting
the previous base image. To roll back a single image:

1. Revert that file in `aqp_platform/Dockerfile` or
   `aqp_platform/build/docker/<service>/Dockerfile` to its
   pre-Phase-2 state.
2. Trigger `build-multi-arch.yml` on the revert branch.
3. The cosign keyless signature still applies (it signs by digest,
   not base image). The grype scan may fail differently because
   the Debian-slim base ships different CVEs.

## Cosign signing on PRs

The Phase 2 §5.2 cosign + SBOM + grype steps gate on
`if: github.event_name != 'pull_request'` because cosign keyless
requires OIDC, which is unavailable on PRs from forked
repositories. PRs from internal branches still build (and pull-
through cache), but they neither push nor sign. The `inspect` job
that runs `cosign verify` on `:latest` tags is only useful for
merged commits.

If you need to verify a signature on a PR build, push to a feature
branch in the canonical repo (not a fork) and check the registry
manually:

```bash
docker pull docker.io/julianwiley/aqp-api:feat-phase-2-supply-chain-<sha>
cosign verify \
  --certificate-identity-regexp 'https://github.com/julianwiley/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  docker.io/julianwiley/aqp-api:feat-phase-2-supply-chain-<sha>
```

## Related documents

- [RESTRUCTURING_PLAN.md §5](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md)
- [aqp_platform/deployments/kubernetes/security/README.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp_platform/deployments/kubernetes/security/README.md)
- [`.cursor/plans/aqp-index-debt-phase-2-supply-chain.md`](https://github.com/julianwiley/agentic_quant_platform/blob/main/.cursor/plans/aqp-index-debt-phase-2-supply-chain.md)
- ADR 007 — QuantBot Latency Classes (explains the HFT Debian-slim exemption)
