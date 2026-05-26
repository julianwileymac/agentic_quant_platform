# DR replay runbook

Disaster-recovery rehearsal procedure for AQP. Targets:

- **RPO 1 hour** for `aqp_admin` + control-plane services.
- **RTO 4 hours** for the same.
- **RPO 15 minutes** for trading-relevant data.
- **RTO 1 hour** for the same.

The exercise is run quarterly (calendar reminder owned by the
platform team). The first exercise is scheduled for the end of
Phase 5 of the multi-account overhaul.

## Pre-requisites

- AWS Organizations + Control Tower applied (Phase 4 complete).
- ArgoCD app-of-apps applied to dev + staging + prod clusters.
- Velero installed on every workload cluster (chart at
  [aqp_platform/deployments/kubernetes/helm/velero](../../../aqp_platform/deployments/kubernetes/helm/velero/)).
- ECR cross-region replication active to `us-west-2`.
- RDS cross-region read replica green.
- S3 CRR active on every Parquet + audit-archive bucket.
- Route 53 health-check failover record set on the
  `manage.aqp.fund` ingress.

## Steps

### 1. Trigger the failure

Pick the rehearsal target — typically `aqp-dev` (never prod).
Document the start time in the incident ticket.

```bash
# Disable the dev cluster's API server (simulates a control-plane outage).
aws eks update-cluster-config \
  --name aqp-dev \
  --region us-east-1 \
  --resources-vpc-config endpointPrivateAccess=false,endpointPublicAccess=false
```

### 2. Confirm impact

`aqp_admin` should now show `unreachable` for the dev cluster
under `/admin/kubernetes/status`. The KillSwitch should still
work because it fans out to other clusters too.

### 3. Bring up the replay cluster

```bash
cd infrastructure/envs/dev
terraform apply -var-file=terraform.tfvars
```

This re-creates the EKS cluster with the same name + node groups.
ArgoCD picks up the new cluster via its Cluster generator (label
`aqp.io/managed=true`).

### 4. Replay state from Velero

```bash
velero backup-location get
velero restore create dr-replay-$(date +%s) \
  --from-backup daily-full-$(velero backup get | tail -1 | awk '{print $1}')
```

### 5. Restore RDS

The cross-region read replica in `us-west-2` is promoted to
primary; the DR replay points the dev cluster's RDS DSN at the
new primary. The Postgres instance comes up with the audit ledger
intact so no admin actions are lost.

### 6. Verify

- `aqp_admin` health should return 200 within 4h.
- The audit ledger should show the gap as a single contiguous
  block (no missing rows beyond the RPO window).
- Paper-trading runs that were active are stamped `status=halted`
  by the watchdog.
- The ArgoCD app-of-apps sync should converge within 15min after
  the cluster comes back.

### 7. Document

Append to the rehearsal log at
`aqp_docs/docs/operations/dr-rehearsal-log.md` with:

- Start / end timestamps.
- Actual RPO + RTO measured.
- Issues encountered + remediations.
- Sign-off from the security officer.
