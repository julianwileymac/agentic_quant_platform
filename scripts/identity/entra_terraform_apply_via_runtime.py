"""Apply the aqp_entra_directory stack via TerraformRuntime (rule 42).

Workstream "Entra internal tenant"
(docs/plans/entra-internal-tenant-rollout.md). The script:

1. Loads the ``entra-internal`` :class:`TerraformStackSpec` from
   ``aqp_platform/configs/terraform/stacks/entra-internal.yaml``.
2. Constructs a :class:`TerraformRuntime` keyed on the configured
   workspace.
3. Runs ``runtime.plan(...)`` followed by an interactive
   "yes/NO" confirmation prompt before ``runtime.apply(...)``.

Every step writes the standard ``terraform_runs`` audit row via
:class:`TerraformRuntime`. NEVER call ``terraform apply`` directly
outside this helper or the CI workflow at
``.github/workflows/entra-terraform.yml``.

Usage:

    python scripts/identity/entra_terraform_apply_via_runtime.py \\
        --workspace wiley-tech --reason "Phase 1 land"

    # Plan-only (no apply, no prompt):
    python scripts/identity/entra_terraform_apply_via_runtime.py \\
        --workspace wiley-tech --plan-only

    # Auto-confirm (CI usage; emits a warning):
    python scripts/identity/entra_terraform_apply_via_runtime.py \\
        --workspace wiley-tech --reason "..." --apply --yes

The script prints redacted output only — token-bearing fields are
replaced with their first 4 characters per AGENTS rule 26.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("entra_terraform_apply")


REPO_ROOT = Path(__file__).resolve().parents[2]
STACK_YAML = (
    REPO_ROOT
    / "aqp_platform"
    / "configs"
    / "terraform"
    / "stacks"
    / "entra-internal.yaml"
)


def _safe_summary(out: Any) -> dict[str, Any]:
    """Redact any field whose name suggests a secret. AGENTS rule 26."""
    if not isinstance(out, dict):
        return {"raw": str(out)[:200]}
    redacted: dict[str, Any] = {}
    secret_markers = (
        "password",
        "secret",
        "token",
        "key",
        "credential",
        "private",
        "authorization",
        "kubeconfig",
    )
    for k, v in out.items():
        lk = str(k).lower()
        if any(m in lk for m in secret_markers):
            if isinstance(v, str) and v:
                redacted[k] = f"{v[:4]}\u2026"
            else:
                redacted[k] = "<redacted>"
        elif isinstance(v, dict):
            redacted[k] = _safe_summary(v)
        elif isinstance(v, list):
            redacted[k] = [
                _safe_summary(item) if isinstance(item, dict) else item for item in v
            ]
        else:
            redacted[k] = v
    return redacted


def _load_spec(stack_yaml: Path):
    """Load + validate the TerraformStackSpec from the YAML."""
    if not stack_yaml.exists():
        raise FileNotFoundError(
            f"stack yaml not found at {stack_yaml}; check repo layout"
        )
    # Lazy imports so ``--help`` works without the AQP runtime.
    from aqp.terraform.spec import load_spec_from_yaml  # type: ignore[import-not-found]

    return load_spec_from_yaml(stack_yaml)


def _construct_runtime(spec: Any, *, workspace: str, started_by: str) -> Any:
    from aqp.auth.context import RequestContext  # type: ignore[import-not-found]
    from aqp.terraform.runtime import TerraformRuntime  # type: ignore[import-not-found]

    context = RequestContext(
        user_id=started_by,
        org_id=None,
        workspace_id=workspace,
        cell_id=None,  # control-plane stack; no cell binding
    )
    return TerraformRuntime(
        spec=spec,
        workspace_id=workspace,
        context=context,
    )


def _confirm(reason: str, yes: bool) -> bool:
    if yes:
        logger.warning(
            "auto-confirm enabled (--yes). Reason recorded: %s", reason
        )
        return True
    sys.stdout.write(
        "\n"
        "About to APPLY the entra-internal Terraform stack.\n"
        "  Stack: aqp_entra_directory (3 app regs, 7 groups, 7 roles, "
        "GitHub OIDC, named locations)\n"
        f"  Reason: {reason}\n"
        f"  Workspace: {os.environ.get('AQP_TF_WORKSPACE', 'wiley-tech')}\n"
        "Continue? Type ``yes`` to proceed, anything else to abort: "
    )
    sys.stdout.flush()
    answer = sys.stdin.readline().strip().lower()
    return answer == "yes"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="entra_terraform_apply_via_runtime",
        description=(
            "Apply the AQP staff Entra ID Terraform stack via "
            "TerraformRuntime. Always-audited path."
        ),
    )
    parser.add_argument(
        "--workspace",
        default="wiley-tech",
        help="Terraform workspace slug (default: wiley-tech).",
    )
    parser.add_argument(
        "--reason",
        required=False,
        default="",
        help="Free-text reason persisted to terraform_runs.metadata.",
    )
    parser.add_argument(
        "--started-by",
        default=os.environ.get("USER", "unknown"),
        help="User id to associate with the run row (default: $USER).",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Run plan only; do not apply or prompt.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Run apply after plan succeeds. Required for non-plan-only invocations.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Auto-confirm the apply prompt. Reserved for CI; the script "
            "logs a warning when used."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.plan_only and not args.apply:
        logger.error(
            "specify either --plan-only OR --apply (no implicit applies)"
        )
        return 1
    if args.apply and not args.reason:
        logger.error("--apply requires --reason for the audit row")
        return 1

    os.environ.setdefault("AQP_TF_WORKSPACE", args.workspace)

    spec = _load_spec(STACK_YAML)
    runtime = _construct_runtime(
        spec, workspace=args.workspace, started_by=args.started_by
    )

    logger.info("running terraform plan against workspace %s", args.workspace)
    plan_outputs = runtime.plan(started_by_user_id=args.started_by)
    logger.info("plan summary: %s", json.dumps(_safe_summary(plan_outputs), indent=2))

    if args.plan_only:
        return 0

    if not _confirm(args.reason or "<no reason supplied>", yes=args.yes):
        logger.error("apply aborted by operator")
        return 2

    logger.info("running terraform apply against workspace %s", args.workspace)
    apply_outputs = runtime.apply(
        started_by_user_id=args.started_by,
        approver_user_id=args.started_by,
    )
    logger.info("apply outputs: %s", json.dumps(_safe_summary(apply_outputs), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
