---
title: 'HFT Node Onboarding'
summary: '- Bare-metal or near-bare-metal hardware with: - Hardware-timestamping NIC (Intel I210/X710, Mellanox ConnectX-5/6/7). - At least 2 NUMA nodes (most modern dual-socket Xeons / Epycs). - 2 MiB HugePage...'
owner: sre-team
last_reviewed: 2026-05-25
audience: both
---

# HFT Node Onboarding

> How to bring up a new dedicated node for `Frequency.HFT` bots.
> Runtime audience: SRE + platform team.

## Pre-requisites

- Bare-metal or near-bare-metal hardware with:
  - Hardware-timestamping NIC (Intel I210/X710, Mellanox ConnectX-5/6/7).
  - At least 2 NUMA nodes (most modern dual-socket Xeons / Epycs).
  - 2 MiB HugePages support (kernel default).
  - SR-IOV-capable NIC.
- Linux kernel >= 5.10 with PTP support (`ptp4l` + `phc2sys` from
  `linuxptp`).
- The node is already a member of the cluster and runs the standard
  kubelet.

## 1. Taint + label the node

```bash
kubectl taint nodes <node-name> quantbot.io/hft=true:NoSchedule
kubectl label nodes <node-name> quantbot.io/hft=true
```

## 2. Apply the kubelet override

The kubelet config drop-in lives at
`aqp_platform/deployments/kubernetes/hft-nodes/kubelet-config.yaml`.
On systemd hosts:

```bash
sudo cp kubelet-config.yaml /etc/kubernetes/kubelet/kubelet.conf.d/quantbot-hft.conf
sudo systemctl restart kubelet
```

Verify:

```bash
kubectl get --raw "/api/v1/nodes/<node-name>/proxy/configz" | jq .kubeletconfig.cpuManagerPolicy
# Expect: "static"
```

## 3. Allocate HugePages

```bash
kubectl apply -f aqp_platform/deployments/kubernetes/hft-nodes/hugepages-allocation.yaml
# DaemonSet runs once per HFT node and sets nr_hugepages=1024.
```

## 4. Bring up PTP

```bash
kubectl apply -f aqp_platform/deployments/kubernetes/hft-nodes/ptp-config.yaml
```

Verify clock discipline (run inside the `quantbot-ptp` pod):

```bash
kubectl exec -n aqp-bots quantbot-ptp-<pod-id> -c phc2sys -- \
  pmc -u -b 0 'GET CURRENT_DATA_SET' | grep masterOffset
# Expect masterOffset around 0 (sub-microsecond on a healthy network).
```

## 5. Configure SR-IOV

If the SR-IOV Network Operator is installed:

```bash
kubectl apply -f aqp_platform/deployments/kubernetes/hft-nodes/sr-iov-config.yaml
```

Verify VFs are exposed:

```bash
kubectl get nodes <node-name> -o json | jq '.status.allocatable | with_entries(select(.key | startswith("openshift.io/quantbot_hft_vf")))'
```

## 6. Apply the tuned profile

```bash
kubectl apply -f aqp_platform/deployments/kubernetes/hft-nodes/node-tuning-operator.yaml
```

## 7. Validate the node passes the operator's HFT check

The QuantBot Operator's validating webhook will refuse to schedule
an HFT bot on a node that fails any of:

- `quantbot.io/hft` label present
- PTP DaemonSet pod running on the node
- HugePages allocation >= the bot's request
- SR-IOV VF available

Run the operator's diagnostics:

```bash
aqp-bots validate <hft-bot-slug>
```

A passing validation prints `valid: true` and no failure entries.

## Rollback

To take the node out of the HFT pool:

```bash
kubectl drain <node-name> --ignore-daemonsets=false --delete-emptydir-data
kubectl taint nodes <node-name> quantbot.io/hft=true:NoSchedule-
kubectl label nodes <node-name> quantbot.io/hft-
```

The HFT DaemonSets (ptp, hugepages, sriov) auto-stop on the node.
