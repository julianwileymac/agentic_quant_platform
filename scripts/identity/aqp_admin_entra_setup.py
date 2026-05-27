"""Wire aqp_admin to the AQP staff Entra tenant.

Reads the Terraform outputs from the
``aqp_platform/terraform/environments/wiley-tech`` workspace (or
accepts them via flags), then:

1. Validates the values look like real Entra ids.
2. Prints the exact backend (``AQP_*``) + frontend (``NEXT_PUBLIC_*``)
   env vars the operator needs to set.
3. Optionally writes a ``.env.aqp_admin.entra`` file matching those
   env vars.
4. Prints the canonical setup runbook so the operator can move
   straight from this script's output to a working login.

Usage::

    # Auto-discover from the Terraform state (default):
    python scripts/identity/aqp_admin_entra_setup.py

    # Override:
    python scripts/identity/aqp_admin_entra_setup.py \\
        --tenant-id 00000000-1111-2222-3333-444444444444 \\
        --client-id 55555555-6666-7777-8888-999999999999 \\
        --audience  api://aqp-manage-api

    # Write the .env.aqp_admin.entra file:
    python scripts/identity/aqp_admin_entra_setup.py --write-env

    # Skip the runbook print (CI usage):
    python scripts/identity/aqp_admin_entra_setup.py --quiet

The script never prints client secrets — federated credentials are
the canonical CI path (rollout plan §3.5). It also never queries
Microsoft Graph; pair with ``verify_entra_login.py`` for an
end-to-end smoke test.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("aqp_admin_entra_setup")

REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_ENV_DIR = (
    REPO_ROOT / "aqp_platform" / "terraform" / "environments" / "wiley-tech"
)
DEFAULT_ENV_PATH = REPO_ROOT / ".env.aqp_admin.entra"

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@dataclass(slots=True)
class EntraSetup:
    """Resolved Entra ID configuration for the admin BFF + SPA."""

    tenant_id: str
    tenant_domain: str
    staff_app_client_id: str
    manage_api_audience: str
    admin_api_url: str
    admin_origin: str

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def issuer(self) -> str:
        return f"{self.authority}/v2.0"

    def to_backend_env(self) -> dict[str, str]:
        return {
            "AQP_ADMIN_AUTH_PROVIDER": "msal_entra",
            "AQP_ADMIN_AUTH_REQUIRED": "true",
            "AQP_AUTH_MSAL_INTERNAL_TENANT_ID": self.tenant_id,
            "AQP_AUTH_MSAL_INTERNAL_APP_ID": self.staff_app_client_id,
            "AQP_AUTH_MSAL_INTERNAL_AUDIENCE": self.manage_api_audience,
            "AQP_AUTH_OIDC_AUDIENCE": self.manage_api_audience,
            "AQP_ADMIN_ENTRA_TENANT": self.tenant_id,
            "AQP_ADMIN_ENTRA_REDIRECT_PATH": "/api/auth/entra/callback",
        }

    def to_frontend_env(self) -> dict[str, str]:
        return {
            "NEXT_PUBLIC_AQP_AUTH_PROVIDER": "msal_entra",
            "NEXT_PUBLIC_AQP_ADMIN_API_URL": self.admin_api_url,
        }


# ---------------------------------------------------------------------------
# Terraform-output discovery
# ---------------------------------------------------------------------------


def _terraform_output(name: str) -> str:
    if not TERRAFORM_ENV_DIR.exists():
        return ""
    try:
        proc = subprocess.run(
            ["terraform", f"-chdir={TERRAFORM_ENV_DIR}", "output", "-raw", name],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _discover_from_terraform() -> dict[str, str]:
    """Best-effort read of the wiley-tech outputs. Empty strings on miss."""
    return {
        "tenant_id": _terraform_output("entra_tenant_id"),
        "staff_app_client_id": _terraform_output("entra_staff_app_client_id"),
        "manage_api_audience": _terraform_output("entra_manage_api_identifier_uri"),
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate(setup: EntraSetup, *, strict: bool) -> list[str]:
    errors: list[str] = []
    if not UUID_PATTERN.match(setup.tenant_id.lower()):
        errors.append(f"tenant_id {setup.tenant_id!r} is not a valid UUID")
    if not UUID_PATTERN.match(setup.staff_app_client_id.lower()):
        errors.append(
            f"staff_app_client_id {setup.staff_app_client_id!r} is not a valid UUID"
        )
    if not setup.manage_api_audience.startswith(("api://", "https://")):
        errors.append(
            f"manage_api_audience {setup.manage_api_audience!r} should be "
            f"'api://...' or 'https://...'"
        )
    if not setup.admin_origin.startswith(("http://", "https://")):
        errors.append(
            f"admin_origin {setup.admin_origin!r} must be a valid http(s) URL"
        )
    if strict and errors:
        for e in errors:
            logger.error(e)
    return errors


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _print_env_block(title: str, env: dict[str, str]) -> None:
    print(f"# --- {title} ---")
    for key, value in env.items():
        print(f"{key}={value}")
    print()


def _write_env_file(path: Path, setup: EntraSetup) -> None:
    lines: list[str] = [
        "# Generated by scripts/identity/aqp_admin_entra_setup.py.",
        "# Source this file before booting aqp_admin:",
        f"#   set -a; source {path.name}; set +a",
        "",
        "# --- Backend (aqp_admin BFF) ---",
    ]
    for key, value in setup.to_backend_env().items():
        lines.append(f"{key}={value}")
    lines += ["", "# --- Frontend (aqp_admin/frontend Next.js) ---"]
    for key, value in setup.to_frontend_env().items():
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("wrote %s (%d lines)", path, len(lines))


def _print_runbook(setup: EntraSetup, env_file: Path | None) -> None:
    print("=" * 78)
    print("Setup runbook")
    print("=" * 78)
    print()
    print(f"Tenant id        : {setup.tenant_id}")
    print(f"Tenant domain    : {setup.tenant_domain}")
    print(f"Staff app client : {setup.staff_app_client_id}")
    print(f"Manage API aud   : {setup.manage_api_audience}")
    print(f"Authority        : {setup.authority}")
    print(f"Issuer           : {setup.issuer}")
    print(f"Admin BFF origin : {setup.admin_origin}")
    print()
    print("Step 1 - Plan + apply the Entra Terraform stack (if not already):")
    print("  ./scripts/identity/entra_terraform_plan.sh")
    print(
        "  python scripts/identity/entra_terraform_apply_via_runtime.py "
        "--workspace wiley-tech --apply --reason 'admin bootstrap'"
    )
    print()
    print("Step 2 - Grant admin consent for the staff app's Graph permissions:")
    print(
        f"  ./scripts/identity/grant_admin_consent.sh {setup.staff_app_client_id}"
    )
    print()
    print("Step 3 - Stamp the EntraTenantLink as 'internal':")
    print(
        f"  AQP_AUTH_MSAL_INTERNAL_TENANT_ID={setup.tenant_id} \\\n"
        f"  AQP_AUTH_MSAL_INTERNAL_TENANT_DOMAIN={setup.tenant_domain} \\\n"
        "    python scripts/identity/seed_entra_internal_tenant.py --apply"
    )
    print()
    print("Step 4 - Export the admin env vars:")
    if env_file is not None:
        print(f"  set -a; source {env_file.relative_to(REPO_ROOT)}; set +a")
    else:
        print("  (paste the env vars printed above into your shell or k8s deploy)")
    print()
    print("Step 5 - Boot the admin BFF and verify:")
    print("  uv run aqp-admin       # or: python -m aqp_admin.main")
    print(
        f"  curl -fsSL {setup.admin_api_url}/admin/auth/discovery | jq ."
    )
    print(f"  curl -fsSL {setup.admin_api_url}/admin/auth/health    | jq .")
    print()
    print("Step 6 - Boot the admin frontend and round-trip a login:")
    print("  cd aqp_admin/frontend && pnpm dev")
    print(f"  open {setup.admin_origin}")
    print()
    print("Step 7 - End-to-end MSAL smoke test:")
    print("  python scripts/identity/verify_entra_login.py")
    print()
    print("Rollback (hot path - within 5 minutes of a bad change):")
    print("  kubectl set env -n aqp deploy/aqp-admin AQP_AUTH_MSAL_PRIORITY=9999")
    print()
    print("Full rollout plan + risks:")
    print("  docs/plans/entra-internal-tenant-rollout.md")
    print("  aqp_docs/docs/how-to/aqp-admin-entra-setup.md")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aqp_admin_entra_setup",
        description=(
            "Print + optionally write the env vars that wire aqp_admin "
            "against the AQP staff Entra tenant."
        ),
    )
    parser.add_argument("--tenant-id", default="")
    parser.add_argument(
        "--tenant-domain",
        default=os.environ.get(
            "AQP_AUTH_MSAL_INTERNAL_TENANT_DOMAIN", "wiley-tech.onmicrosoft.com"
        ),
    )
    parser.add_argument("--client-id", default="", help="aqp-staff app client id")
    parser.add_argument(
        "--audience",
        default="api://aqp-manage-api",
        help="manage API token audience",
    )
    parser.add_argument(
        "--admin-api-url",
        default=os.environ.get("AQP_ADMIN_API_URL", "http://localhost:8900"),
        help="aqp_admin BFF base URL the SPA fetches /admin/auth/discovery from",
    )
    parser.add_argument(
        "--admin-origin",
        default=os.environ.get(
            "AQP_ADMIN_FRONTEND_ORIGIN", "http://localhost:3001"
        ),
        help="aqp_admin Next.js frontend origin (used for the redirect URI)",
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write a .env.aqp_admin.entra file alongside the printout.",
    )
    parser.add_argument(
        "--env-path",
        default=str(DEFAULT_ENV_PATH),
        help=f"Path for --write-env (default: {DEFAULT_ENV_PATH}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of human-readable env blocks.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the runbook output (useful in CI).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on validation failures.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(message)s",
    )

    discovered = _discover_from_terraform()

    setup = EntraSetup(
        tenant_id=(args.tenant_id or discovered.get("tenant_id") or "").strip(),
        tenant_domain=args.tenant_domain.strip(),
        staff_app_client_id=(
            args.client_id or discovered.get("staff_app_client_id") or ""
        ).strip(),
        manage_api_audience=(
            args.audience or discovered.get("manage_api_audience") or ""
        ).strip(),
        admin_api_url=args.admin_api_url.rstrip("/"),
        admin_origin=args.admin_origin.rstrip("/"),
    )

    errors = _validate(setup, strict=args.strict)
    if errors and args.strict:
        return 2

    if args.json:
        payload = {
            "backend_env": setup.to_backend_env(),
            "frontend_env": setup.to_frontend_env(),
            "issuer": setup.issuer,
            "authority": setup.authority,
            "errors": errors,
        }
        print(json.dumps(payload, indent=2))
    else:
        _print_env_block("Backend env (aqp_admin BFF)", setup.to_backend_env())
        _print_env_block("Frontend env (aqp_admin/frontend)", setup.to_frontend_env())
        if errors:
            print("# Validation warnings:")
            for e in errors:
                print(f"#   {e}")
            print()

    env_file: Path | None = None
    if args.write_env:
        env_file = Path(args.env_path).resolve()
        _write_env_file(env_file, setup)

    if not args.quiet and not args.json:
        _print_runbook(setup, env_file)

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
