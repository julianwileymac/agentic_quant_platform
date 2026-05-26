"""Terraform IaC runtime — owned by ``aqp_control_plane`` after rule 42 modification.

The rule-42 modification (Phase 0.1) moves canonical ownership of the
Terraform lifecycle from the monolith into the management service.
The CP-native :class:`TerraformRuntime` here:

- Mirrors the surface of the legacy ``aqp.terraform.runtime.TerraformRuntime``
  (plan / apply / destroy / refresh / state_pull / validate / import / unlock).
- Persists ``terraform_runs`` rows via the
  :class:`aqp_platform_core.runtime.workload.WorkloadRuntime` audit
  lifecycle (action = ``WorkloadAction.TERRAFORM_*``).
- Emits progress via the pluggable
  :class:`aqp_platform_core.runtime.progress.ProgressEmitter`
  (Redis bridge in the monolith, structured log in the CP sidecar).
- Honours the kill-switch via :meth:`WorkloadRuntime.halt_all`.

Rollout: gated by ``AQP_TERRAFORM_USE_CONTROL_PLANE``. The legacy
in-monolith :class:`aqp.terraform.runtime.TerraformRuntime` stays
active until every internal call-site has flipped to the brokered
path. See ``.cursor/plans/aqp-index-debt-control-plane-maturation.md``
for the decommission timeline.
"""
from __future__ import annotations

from aqp_cp.terraform.audit_sink import (
    HttpTerraformAuditSink,
    NullTerraformAuditSink,
    TerraformAuditSink,
)
from aqp_cp.terraform.policy import PolicyCheckResult, check_plan_against_opa
from aqp_cp.terraform.runtime import (
    TerraformExecutor,
    TerraformRuntime,
    TerraformRuntimeError,
)

__all__ = [
    "HttpTerraformAuditSink",
    "NullTerraformAuditSink",
    "PolicyCheckResult",
    "TerraformAuditSink",
    "TerraformExecutor",
    "TerraformRuntime",
    "TerraformRuntimeError",
    "check_plan_against_opa",
]
