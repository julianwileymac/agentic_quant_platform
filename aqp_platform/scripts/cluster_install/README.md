# aqp_platform/scripts/cluster_install/ - AQP-owned cluster bootstrap automation

The AQP control plane is the canonical owner of every shared cluster
service. This directory holds the Helm install + bootstrap scripts that
prepare a Kubernetes cluster (rpi, EKS, AKS, GKE, vanilla k3s, ...) to
run the AQP workload manifests under `aqp_platform/deployments/kubernetes/`.

These scripts were lifted from `rpi_kubernetes/bootstrap/scripts/` and
`rpi_kubernetes/kubernetes/bootstrap/helm-runner/` during the rpi <->
AQP decoupling so AQP no longer depends on rpi_kubernetes content for
shared-infra provisioning.

## Layout

```
aqp_platform/scripts/cluster_install/
|-- README.md                           (this file)
|-- helm-runner/                        (in-cluster helm install Jobs for kserve / dagster / airbyte)
|-- install-redpanda.sh                 (operator + Redpanda CR)
|-- install-kube-prometheus-stack.sh    (Prometheus + Grafana + Alertmanager)
|-- install-opentelemetry-operator.sh   (operator + Instrumentation CR)
|-- install-phoenix.sh                  (Phoenix + Postgres backend)
|-- install-spark-operator.sh           (Spark + Hudi job submitter)
|-- install-questdb.sh                  (QuestDB StatefulSet apply + bucket bootstrap)
|-- install-redpanda-connect.sh         (Redpanda Connect with QuestDB sink)
|-- install-flink.sh / install-flink.ps1
|-- install-loki.sh / install-loki.ps1
|-- install-redis.sh / install-redis.ps1
|-- install-alphavantage.sh / install-alphavantage.ps1
|-- sync-helm-values.ps1
|-- fix-grafana.ps1
|-- build-flink-jobs.sh / build-flink-jobs-java.sh
`-- verify-minio.sh
```

Each script targets the AQP-owned `aqp-*` namespaces (`aqp-data-services`,
`aqp-streaming`, `aqp-elt`, `aqp-mlops`, `aqp-observability`,
`aqp-lakehouse`, `aqp-edge`). They are idempotent: re-running is a no-op
when the HelmRelease / kustomization is already present at the expected
version.

## Prerequisites

- `kubectl` 1.30+ pointing at the target cluster.
- `helm` 3.14+.
- `cluster-admin` for the active context (operators install CRDs).
- A container registry the cluster can pull from for the AQP app images
  (separate prerequisite documented in
  `aqp_docs/operations/kubernetes-deploy.md`).

The cluster bootstrap itself (k3s install, node prep, USB SSD mounts on
RPi hardware) stays in `rpi_kubernetes/bootstrap/` because it is
RPi-specific. Cloud and other-k3s clusters use their own bootstrap
(eksctl, az aks, gcloud, k3sup, ...).

## Usage

Install the operators / Helm charts that AQP's manifests depend on:

```bash
bash aqp_platform/scripts/cluster_install/install-redpanda.sh
bash aqp_platform/scripts/cluster_install/install-questdb.sh
bash aqp_platform/scripts/cluster_install/install-redpanda-connect.sh
bash aqp_platform/scripts/cluster_install/install-kube-prometheus-stack.sh
bash aqp_platform/scripts/cluster_install/install-opentelemetry-operator.sh
bash aqp_platform/scripts/cluster_install/install-phoenix.sh
bash aqp_platform/scripts/cluster_install/install-spark-operator.sh
bash aqp_platform/scripts/cluster_install/install-flink.sh
bash aqp_platform/scripts/cluster_install/install-loki.sh
bash aqp_platform/scripts/cluster_install/install-redis.sh
```

Then apply the AQP manifests:

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/base/
```

For the two-node tower+laptop bootstrap flow, apply the thin dev slice first:

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/tower-dev/
```

The `helm-runner/` kustomization can be applied if you want to install
Helm charts (kserve, dagster, airbyte) from inside the cluster instead
of from a workstation.
