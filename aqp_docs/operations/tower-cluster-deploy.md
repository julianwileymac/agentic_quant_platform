# Tower Two-Node Cluster Deploy

Deploy AQP to the dedicated two-node cluster (`aqp-tower` control plane +
`aqp-laptop` WSL2 agent) before any portal migration work.

## Scope

- In scope: AQP stack bootstrap (`tower-dev`), QuestDB, control-plane wiring.
- Out of scope: `julianwiley-portal` migration (deferred; owned by `rpi_kubernetes`).

## Prerequisites

- Two-node cluster already online and `kubectl get nodes` shows both `Ready`.
- Context points to the tower cluster.
- Auth0 tenant + client values set in `aqp_platform/deployments/kubernetes/base/configmaps`.
- Secrets rendered for:
  - `aqp-secrets` (`aqp` namespace)
  - `aqp-admin-secrets` (`aqp-admin` namespace)

## 1) Install cluster dependencies

```bash
bash aqp_platform/scripts/cluster_install/install-redpanda.sh
bash aqp_platform/scripts/cluster_install/install-questdb.sh
bash aqp_platform/scripts/cluster_install/install-redpanda-connect.sh
```

Optional (if your target slice needs them): OpenTelemetry, kube-prometheus-stack,
Phoenix, Spark Operator.

## 2) Apply the thin tower overlay

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/tower-dev/
```

This slice includes:

- core workloads (`aqp-core`, `aqp-worker`, `aqp-client`, `aqp-cp`)
- `redis-master`
- `postgres-shared`
- `questdb` (dev-sized PVC, relaxed scheduling)

## 3) Verify

```bash
bash scripts/verify_tower_cluster.sh
```

## 4) Terraform target wiring (optional but recommended)

```bash
# Preview
python -m aqp.cli.main deploy --target tower --action plan

# Apply
python -m aqp.cli.main deploy --target tower --action apply
```

## Rollback

```bash
kubectl delete -k aqp_platform/deployments/kubernetes/overlays/tower-dev/
```

Then restore the previous known-good overlay or Terraform state.
