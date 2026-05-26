# `infrastructure/policies/rego`

Rego policy bundle evaluated by `conftest test` in
[`.github/workflows/terraform-pipeline.yml`](../../../.github/workflows/terraform-pipeline.yml)
against every Terraform plan.

## Files

| File | Scope |
| --- | --- |
| `baseline.rego` | Security-baseline rules every plan MUST pass (public S3, encryption, IAM wildcards, ECR mutability, TLS minimums, log retention). |
| `cost.rego` | Cost guardrails (oversize RDS, per-AZ NAT, large ElastiCache clusters). Per-resource `aqp.io/cost-override` tag escapes the deny. |

## Invocation

The workflow runs (from `infrastructure/` working dir):

```bash
./conftest test envs/${env}/tfplan --policy policies/rego --output github
```

`deny` (non-empty set) fails the workflow. `warn` (non-empty set)
posts an annotation but does NOT fail. The github output format emits
inline GitHub annotations so PR reviewers see the violations next to
the affected lines.

## Adding a rule

1. Decide whether it's `deny` (hard) or `warn` (advisory).
2. Add the rule to the matching file (security → `baseline.rego`,
   cost → `cost.rego`).
3. Write a clear `msg` — it surfaces in the PR check + the SCP audit
   log. Include the resource address so reviewers can `Ctrl+F` find it.
4. Add a fixture under `tests/` (per-rule test plans) if the rule has
   non-trivial conditions.

## Bypass

Per-resource bypass: add a tag on the resource:

```hcl
tags = {
  "aqp.io/cost-override" = "approved-by-cfo"  # or
  "aqp.io/security-override" = "ticket-AQP-1234"
}
```

Per-environment bypass: add to
`infrastructure/policies/rego/exceptions_<env>.rego`. The convention is
that exceptions are explicit + auditable; never edit `baseline.rego`
to soft-disable a rule.
