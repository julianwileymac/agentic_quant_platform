# AQP security overlay

Phase 2 §5.3 + §5.4 of [RESTRUCTURING_PLAN.md](../../../../RESTRUCTURING_PLAN.md).

This overlay owns the cluster-wide security plane for AQP-managed
namespaces:

- [`kyverno/cluster-policies/`](kyverno/cluster-policies/) — six
  Kyverno `ClusterPolicy` objects that enforce the Phase 2 §5.3
  controls (signature verification, PSS restricted labels, gVisor
  RuntimeClass, no host network, no privilege escalation, required
  k8s + FinOps labels).
- The PSS backfill on AQP-owned `Namespace` YAMLs in
  `../base/`, `../base-services/`, `../mlops/`, `../observability/`,
  `../edge/`, `../bots-operator/` (§5.4).
- The documented exemption list below, which is THE source of
  authority for which namespaces intentionally run with a relaxed
  PSS profile or `hostNetwork: true`.

## Apply

```bash
# Pre-req: install Kyverno itself. The cluster-install script lives at
#   aqp_platform/scripts/cluster_install/install-kyverno.sh
# (Phase 2.5 deliverable). For now, install upstream:
helm repo add kyverno https://kyverno.github.io/kyverno
helm install kyverno kyverno/kyverno \
  --namespace kyverno --create-namespace

# Apply the AQP policy bundle:
kubectl apply -k aqp_platform/deployments/kubernetes/security/

# Verify the policies are registered:
kubectl get clusterpolicy
```

## Audit-first rollout (Phase 2)

Every policy ships with `validationFailureAction: Audit`. Violations
appear in:

1. `kubectl get policyreport -A` — namespace-scoped reports.
2. `kubectl get clusterpolicyreport` — cluster-scoped reports.
3. Prometheus metrics `kyverno_policy_results_total{result="fail"}`
   (scraped by the existing `kube-prometheus-stack` instance under
   `../observability/kube-prometheus-stack/`).

The Phase 2 deliverable is the policies themselves; the Phase 2.5
follow-up is the ratchet to `Enforce`. The ratchet table below
captures the per-policy state.

## Phase 2.5 ratchet plan

| Policy | Current | Target | Gating condition |
| --- | --- | --- | --- |
| [`00-verify-signatures.yaml`](kyverno/cluster-policies/00-verify-signatures.yaml) | Audit | Enforce | All four canonical AQP images (aqp-api, aqp-worker, aqp-client, aqp-control-plane) consistently carry cosign keyless signatures from `.github/workflows/build-multi-arch.yml`. Verified by 7 consecutive days of clean `policyreport` output. |
| [`01-require-pss-restricted.yaml`](kyverno/cluster-policies/01-require-pss-restricted.yaml) | Audit | Enforce | Every AQP-owned namespace either carries the three PSS restricted labels OR carries an explicit `aqp.io/pss-exception` reason. Backfilled in Phase 2 §5.4. |
| [`02-require-runtime-class.yaml`](kyverno/cluster-policies/02-require-runtime-class.yaml) | Audit | Enforce | After Phase 5 §8.3 lands the gVisor RuntimeClass + `aqp_platform/scripts/cluster_install/install-gvisor.sh`. Do NOT flip to Enforce before then — the policy would block ALL Pods that pull `aqp-agent-sandbox` because the RuntimeClass object doesn't exist yet. |
| [`03-no-host-network.yaml`](kyverno/cluster-policies/03-no-host-network.yaml) | Audit | Enforce | After the cloudflared namespace + any Phase 5 edge agent namespace carries `aqp.io/host-network-allowed: "true"`. Backfilled in Phase 2 §5.4. |
| [`04-no-privilege-escalation.yaml`](kyverno/cluster-policies/04-no-privilege-escalation.yaml) | Audit | Enforce | Every AQP-owned Deployment carries `allowPrivilegeEscalation: false`. Already true for `aqp-core`, `aqp-client`, `aqp-worker`, `aqp-cp`, `bots-operator`, `aqp-ide`, `aqp-ui`, `redis-master` per the existing pod specs; only third-party Helm charts may need overrides. |
| [`05-required-labels.yaml`](kyverno/cluster-policies/05-required-labels.yaml) | Audit | Enforce | After the FinOps label backfill on streaming/lakehouse/observability namespaces (currently only `aqp-ui` and `aqp` carry the full quartet). |

## Documented PSS exception list (§5.4)

The Kyverno `01-require-pss-restricted.yaml` policy skips any
Namespace that carries `aqp.io/pss-exception: <reason>`. The
following AQP-owned namespaces are intentional carve-outs:

| Namespace | PSS profile | Reason |
| --- | --- | --- |
| `aqp-streaming` | privileged | Strimzi Kafka brokers (kafka-strimzi/kafka.yaml) require host volume mounts for the JBOD log dirs + Cruise Control's reflection access. |
| `aqp-edge` | privileged | cloudflared Pod requires `cap_net_admin` to bind the tunnel network namespace. Documented at `../edge/cloudflared-aqp/README.md`. |
| `aqp-observability` | privileged | OpenTelemetry collector daemonset binds host metrics + node-level eBPF probes. |
| `aqp-timeseries` | baseline | QuestDB requires `vm.max_map_count` sysctl write via a privileged init container. |
| `aqp-lakehouse` | baseline | Spark Operator's executor Pods require `mlock` capability for low-latency Arrow buffers. |
| `aqp-data-services` | baseline | PostgreSQL Operator (CNPG) requires fsGroupChangePolicy=OnRootMismatch which the `restricted` profile rejects. |
| `aqp-mlops` | baseline | Argo Workflows requires emptyDir mounts that exceed the `restricted` size limit. |
| `aqp-elt` | baseline | Airbyte's workspace Pods run user-provided connector code; PSS restricted is enforced WITHIN the per-connector sandbox in Phase 5 §8. |
| `aqp-ide` | baseline | Theia IDE writes to a per-user home directory + scaffolds notebook outputs; the `restricted` profile blocks `fsGroup` policies that the IDE pod needs. Tracked exception `theia-writable-home`. |
| `aqp-bots` | baseline | The QuantBot Platform's HFT pods exec the Cython SPSC ring extension as a subprocess and need `cap_sys_nice` + writable shm; the `restricted` profile blocks both. Tracked exception `hft-cython-subprocess` per ADR 007. |

Every exception MUST land with the explicit
`aqp.io/pss-exception: <reason>` label on the Namespace AND a row
in this table. Adding an exception without updating both is a
review-blocking change.

## Documented `hostNetwork: true` exception list (§5.4)

The Kyverno `03-no-host-network.yaml` policy skips any Pod in a
namespace carrying `aqp.io/host-network-allowed: "true"`. The
following namespaces are intentional carve-outs:

| Namespace | Why |
| --- | --- |
| `aqp-edge` | cloudflared tunnel requires the host network namespace to bind the egress tunnel interface. |

## UID 65532 exception list (§5.4)

The Phase 2 §5.1 Chainguard migration pins every AQP-owned final
stage to UID 65532. The following images are documented exceptions:

| Image | Reason |
| --- | --- |
| `aqp-edge` (Envoy) | Envoy's upstream distroless image runs as UID 101 (`envoy` user). We `USER 65532:65532` in the AQP wrapper Dockerfile, accepting the small chown cost, to match the rest of the fleet. |
| `aqp-bots` (distroless nonroot) | Already runs as UID 65532 (distroless `nonroot` default). |
| `aqp-bots-hft` (Debian-slim + DPDK/Onload) | Runs as UID 65532 explicitly per `aqp_bots/Dockerfile.hft`. |

## What this overlay does NOT include

- The Kyverno admission controller itself (install via Helm or the
  forthcoming `install-kyverno.sh`).
- gVisor runtime installation on nodes (Phase 5 §8.3).
- SPIRE / SPIFFE workload identity (Phase 4 §7.2).
- Cedar policy engine for application authz (Phase 4 §7.3).
- Pomerium IAP for `/manage/*` (Phase 4 §7.5).

Those are all later phases; this overlay is the Phase 2 admission-time
seam that enforces signed images + PSS + gVisor scheduling + FinOps
labels.

## Verify locally

```bash
# Kustomize builds cleanly:
kubectl kustomize aqp_platform/deployments/kubernetes/security/

# Each policy parses against the kyverno CLI:
for f in aqp_platform/deployments/kubernetes/security/kyverno/cluster-policies/*.yaml; do
  kubectl apply --dry-run=client -f "$f"
done

# Optional: validate against a real cluster's Kyverno admission webhook
# (requires Kyverno installed):
kyverno apply aqp_platform/deployments/kubernetes/security/kyverno/cluster-policies/ \
  --resource aqp_platform/deployments/kubernetes/base/aqp-core/deployment.yaml
```
