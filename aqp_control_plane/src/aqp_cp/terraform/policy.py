"""OPA / Sentinel policy checker for Terraform plans (rule-42 relocation).

When the workspace's policy attachment is hard-mandatory, the CP-side
:class:`TerraformRuntime` gates ``apply`` behind a passing policy
check. The checker mirrors the in-monolith
:mod:`aqp.terraform.policy` module 1:1 — same Rego file layout, same
:class:`PolicyCheckResult` schema, same opt-out semantics when the
OPA binary is missing.

The OPA binary is OPTIONAL — if missing, the checker returns
``PolicyCheckResult(passed=True, skipped=True, reason="opa binary missing")``
so a misconfigured operator doesn't silently block applies. Hard-mandatory
attachments should keep ``opa`` installed in the executor image
(see ``Dockerfile.terraform-executor`` in
``aqp_platform/deployments/kubernetes/terraform-runner/``).

The CP runtime calls this module from its ``_run_apply`` path; the
in-monolith path keeps using :mod:`aqp.terraform.policy` until every
internal call-site flips per the ``AQP_TERRAFORM_USE_CONTROL_PLANE``
flag.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PolicyCheckResult:
    """Outcome of one OPA / Sentinel policy evaluation.

    Identical schema to ``aqp.terraform.policy.PolicyCheckResult`` so
    the monolith's :class:`TerraformPolicyAttachment.last_check_*`
    column writers can ingest either side's result without a shape
    translation layer.
    """

    passed: bool
    skipped: bool = False
    reason: str = ""
    violations: list[dict[str, Any]] = field(default_factory=list)
    raw_output: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "passed": bool(self.passed),
            "skipped": bool(self.skipped),
            "reason": self.reason,
            "violations": list(self.violations),
        }


def check_plan_against_opa(
    *,
    plan_json_path: str | Path,
    policy_path: str | Path,
    package: str = "terraform.aqp",
    rule: str = "deny",
    binary: str | None = None,
    timeout_seconds: float = 120.0,
) -> PolicyCheckResult:
    """Evaluate ``data.<package>.<rule>`` against ``plan_json_path``.

    Conventional Rego layout (one policy file per workspace, package
    pinned to ``terraform.aqp``)::

        package terraform.aqp

        deny[msg] {
            input.resource_changes[_].change.actions[_] == "delete"
            input.resource_changes[_].address == "aws_db_instance.prod"
            msg := "production database is delete-protected"
        }

    Empty ``deny`` set -> ``passed=True``. Non-empty -> ``passed=False``
    with each member captured as a violation.

    The CP-side executor writes the plan JSON to
    ``<workspace_dir>/tfplan.json`` (``terraform show -json``); the
    runtime then resolves the policy bundle URI from the workspace's
    :class:`TerraformPolicyAttachment` row (proxied through the
    monolith via the :class:`HttpAuditSink` chain in audit_sink.py).
    """
    plan = Path(plan_json_path)
    policy = Path(policy_path)
    if not plan.exists():
        return PolicyCheckResult(
            passed=True,
            skipped=True,
            reason=f"plan json missing at {plan_json_path}",
        )
    if not policy.exists():
        return PolicyCheckResult(
            passed=True,
            skipped=True,
            reason=f"policy file missing at {policy_path}",
        )
    opa = binary or shutil.which("opa")
    if not opa:
        return PolicyCheckResult(
            passed=True,
            skipped=True,
            reason="opa binary not found on PATH (install OPA in the runner image)",
        )
    try:
        completed = subprocess.run(  # noqa: S603 - list args, no shell
            [
                opa,
                "eval",
                "--format",
                "json",
                "--input",
                str(plan),
                "--data",
                str(policy),
                f"data.{package}.{rule}",
            ],
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PolicyCheckResult(
            passed=False,
            reason=f"opa eval timed out after {timeout_seconds:.0f}s",
            raw_output="<timeout>",
        )
    except Exception as exc:  # noqa: BLE001
        return PolicyCheckResult(
            passed=False,
            reason=f"opa eval failed to start: {exc}",
            raw_output=str(exc),
        )

    raw = (completed.stdout or b"").decode("utf-8", errors="replace")
    if completed.returncode != 0:
        return PolicyCheckResult(
            passed=False,
            reason=f"opa eval exit_code={completed.returncode}",
            raw_output=raw[:4096],
        )
    try:
        payload = json.loads(raw)
    except Exception:
        return PolicyCheckResult(
            passed=False,
            reason="opa eval returned non-JSON payload",
            raw_output=raw[:4096],
        )

    violations: list[dict[str, Any]] = []
    for entry in payload.get("result") or []:
        for expression in entry.get("expressions") or []:
            value = expression.get("value")
            if isinstance(value, list):
                violations.extend(_normalize_violation(v) for v in value)
            elif isinstance(value, dict):
                violations.append(_normalize_violation(value))

    passed = not violations
    return PolicyCheckResult(
        passed=passed,
        violations=violations,
        reason="" if passed else f"{len(violations)} policy violation(s)",
        raw_output=raw[:4096],
    )


def _normalize_violation(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"message": str(value)}


__all__ = ["PolicyCheckResult", "check_plan_against_opa"]
