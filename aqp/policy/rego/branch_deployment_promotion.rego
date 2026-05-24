package aqp.deploy.branch_promotion

# Reject promotion of a branch deployment into prod unless ALL
# of the following hold:
#
#   1. The originating PR has at least one approving review.
#   2. The PR's CI checks (build + tests + ruff) all pass.
#   3. The branch deployment's RLS budget reservation has been
#      drained well under the configured ceiling (no surprise
#      cost overrun).
#   4. The promoter has the `admin:cluster` scope (Tier-P).
#
# Input shape:
#   { pr_approvals: 1,
#     ci_status: "success" | "failure" | "pending",
#     branch_budget_consumed_pct: 0.42,
#     branch_budget_ceiling_pct: 0.80,
#     promoter_scopes: ["admin:cluster", "data:write"] }

default allow = false

allow {
    input.pr_approvals >= 1
    input.ci_status == "success"
    input.branch_budget_consumed_pct < input.branch_budget_ceiling_pct
    "admin:cluster" in input.promoter_scopes
}
