# SOC 2 Type II evidence map

Mapping from the SOC 2 Trust Services Criteria to the
machine-readable evidence shipped by the AQP overhaul.

This map is the artifact the compliance team hands to the auditor.
It points at the source of truth for every control; the auditor
can pull the evidence directly from S3 / CloudTrail / Postgres
without manual collation.

| Criterion | Control | Evidence source | Where in the repo |
| --- | --- | --- | --- |
| CC6.1 Logical access | All API auth via `IdentityProvider` | `security_audit_events` Postgres + S3 WORM mirror | `aqp/tasks/audit_log_export_tasks.py` |
| CC6.1 (cont.) | RBAC via `Membership` lattice | `Membership` rows + `expand_role` lattice | `aqp_platform_core/src/aqp_platform_core/auth/rbac.py` |
| CC6.6 Step-up MFA | RFC 9470 step-up on every destructive admin route | `step_up_denied` rows in `security_audit_events` | `aqp_admin/src/aqp_admin/deps/stepup.py` |
| CC6.7 Privileged access | Break-glass 4-eyes + 60min auto-expiry | `admin.break_glass.*` audit rows + Security Hub findings | `aqp_admin/src/aqp_admin/services/break_glass.py` |
| CC6.8 Cryptography | TLS 1.3 ingress + Linkerd mTLS internal | ALB security policy `ELBSecurityPolicy-TLS13-1-2-2021-06`; Linkerd identity certs from ACM PCA | `infrastructure/modules/acm-certificates`, `infrastructure/modules/acm-pca` |
| CC7.1 Detection | Falco DaemonSet + custom rules | Falco events shipped to Loki | `aqp_platform/deployments/kubernetes/helm/falco/values.yaml` |
| CC7.2 Monitoring | OpenTelemetry + Prometheus + Loki + Tempo | Per-env Grafana dashboards | `infrastructure/modules/observability-stack` |
| CC7.3 Incident response | KillSwitch fan-out + halt audit rows | `admin.halt.all` rows | `aqp_admin/src/aqp_admin/api/routers/halt.py` |
| CC7.5 Threat intel | Trivy + Grype on every image | Build-time SBOM + provenance | `.github/workflows/build-publish.yml`, `.github/actions/build-sign-push/` |
| CC8.1 Change management | Hash-locked spec versions | `terraform_stack_spec_versions`, `agent_spec_versions`, `bot_versions`, `rl_experiment_versions`, `analysis_spec_versions`, `workflow_spec_versions` | per AGENTS rules 13/15/17/24/41/43 |
| CC8.1 (cont.) | Immutable Alembic migrations | `.hashes.lock` + `check_migration_immutability.py` | `scripts/ci/check_migration_immutability.py` |
| CC9.1 Risk mitigation | SLSA L3 provenance + Cosign keyless | OCI attestations on every image | `.github/workflows/build-publish.yml` |
| A1.2 Recovery procedures | DR replay runbook + Velero schedules | quarterly rehearsal log | `aqp_docs/docs/operations/dr-replay.md` |
| A1.3 Recovery validation | Cross-region S3 CRR + RDS read replica | Lifecycle policies + replication metrics | `infrastructure/envs/prod/main.tf` |
| C1.2 Confidential information | S3 Object Lock + KMS CMK | `aqp-audit-archive-*` bucket policies | `infrastructure/envs/shared-services/main.tf` |
| C1.2 (cont.) | Step-up + RBAC on broker creds | `BrokerCredentialStore` priority 4 | `aqp/credentials/stores/broker_credential_store.py` |
| PI1.1 Processing integrity | Hash-chained `audit_log` table + Postgres trigger | trigger `enforce_audit_log_hash_chain` | `alembic/versions/0079_audit_log_hash_chain.py` |
| P1.1 Privacy notice | n/a (B2B platform; no PII) | n/a | n/a |
| P3.1 Information collection | OIDC scopes + `https://aqp.internal/resources` claim | Auth0 + Entra Action sources | `aqp/auth/providers/` |

## Type II evidence collection cadence

| Cadence | Activity |
| --- | --- |
| Continuous | CloudTrail Org Trail, Config aggregator, GuardDuty, Security Hub findings; all S3 WORM-mirrored with 7-year retention |
| Daily | Audit log export to WORM bucket (Celery beat 02:00 UTC) |
| Weekly | Renovate dependency updates merged to dev; SBOM diff review |
| Monthly | Access review (operator-driven via `/admin/rbac` UI) |
| Quarterly | DR rehearsal per `dr-replay.md`; tabletop incident exercise |
| Annual | SOC 2 Type II audit window (12-month observation) |

## Operator hand-offs

The platform team owns the controls; compliance owns the
evidence collation + auditor liaison. The handoff is via the
`#aqp-compliance` Slack channel + the SOC 2 dashboard in Grafana
(panels driven by Prometheus queries against
`security_audit_events`).
