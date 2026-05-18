"""OPA / Sentinel policy checker for Terraform plans.

When a :class:`TerraformPolicyAttachment` row is bound to a workspace
and ``hard_mandatory=True``, the runtime gates ``apply`` behind a
passing policy check. The checker:

1. Reads the ``tfplan.json`` written by :meth:`TerraformExecutor.plan`.
2. Looks up the policy bundle URI from
   :class:`TerraformPolicyAttachment.policy_set_uri` (currently only
   local-file URIs are supported; remote bundle fetches land in a
   later iteration).
3. Shells out to ``opa eval`` (the only mandatory dep — Sentinel is
   reserved for HCP-managed workspaces).
4. Returns a :class:`PolicyCheckResult` the runtime persists on the
   :class:`TerraformPolicyAttachment.last_check_*` columns.

The OPA binary is OPTIONAL — if missing, the checker returns
``PolicyCheckResult(passed=True, skipped=True, reason="opa binary missing")``
so a misconfigured operator doesn't silently block applies. Hard-mandatory
attachments should keep ``opa`` installed in the runner image.
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
    """Outcome of one OPA / Sentinel policy evaluation."""

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
) -> PolicyCheckResult:
    """Evaluate ``data.<package>.<rule>`` against ``plan_json_path``.

    The conventional Rego layout is one file per policy with::

        package terraform.aqp

        deny[msg] {
            input.resource_changes[_].change.actions[_] == "delete"
            input.resource_changes[_].address == "aws_db_instance.prod"
            msg := "production database is delete-protected"
        }

    Empty ``deny`` set -> ``passed=True``. Non-empty -> ``passed=False``
    with each member captured as a violation.
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
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return PolicyCheckResult(
            passed=False,
            reason="opa eval timed out after 120s",
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
