"""List who holds which Entra app role on the AQP manage API.

Workstream "Entra internal tenant"
(docs/plans/entra-internal-tenant-rollout.md). Read-only audit helper:
queries Microsoft Graph for every ``appRoleAssignment`` granted on
the manage API service principal and prints a structured report.

Output formats:

- ``--format=table`` (default) — pretty rich table.
- ``--format=json`` — machine-readable JSON, used by Compliance for
  evidence bundle generation.
- ``--format=csv`` — CSV ready for HR / Security spreadsheets.

The script uses the service-principal-flow client credentials of
the running operator's ``az login`` session; it never accepts secrets
on the command line.

Usage:

    python scripts/identity/list_entra_app_role_assignments.py
    python scripts/identity/list_entra_app_role_assignments.py --format=json
    python scripts/identity/list_entra_app_role_assignments.py --apps  # also list app object ids
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import subprocess
import sys
from typing import Any

logger = logging.getLogger("list_entra_app_role_assignments")


def _az(*args: str) -> dict | list:
    """Run ``az`` with the supplied args; parse the JSON output."""
    cmd = ["az", *args, "--output", "json"]
    logger.debug("running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
    if not proc.stdout.strip():
        return []
    return json.loads(proc.stdout)


def _resolve_manage_api_sp_id() -> str:
    from aqp.config import settings  # type: ignore[import-not-found]

    audience = (settings.auth_msal_internal_audience or "").strip()
    if not audience:
        raise SystemExit(
            "AQP_AUTH_MSAL_INTERNAL_AUDIENCE is empty; set it to the "
            "Terraform output ``manage_api_identifier_uri`` (e.g. "
            "api://aqp-manage-api)."
        )
    apps = _az("ad", "app", "list", "--identifier-uri", audience)
    if not apps:
        raise SystemExit(f"no Entra app found with identifier URI {audience!r}")
    if isinstance(apps, list):
        app = apps[0]
    else:
        app = apps
    sp = _az("ad", "sp", "list", "--filter", f"appId eq '{app['appId']}'")
    if not sp:
        raise SystemExit(
            f"no service principal found for appId {app['appId']!r}"
        )
    return sp[0]["id"] if isinstance(sp, list) else sp["id"]


def _gather_assignments(sp_id: str) -> list[dict[str, Any]]:
    """Return ``appRoleAssignedTo`` rows enriched with role + principal names."""
    raw = _az(
        "rest",
        "--method",
        "GET",
        "--url",
        f"https://graph.microsoft.com/v1.0/servicePrincipals/{sp_id}"
        "/appRoleAssignedTo",
    )
    rows = raw.get("value", []) if isinstance(raw, dict) else []

    # Build a map of role id -> role display name from the SP itself.
    sp_doc = _az(
        "rest",
        "--method",
        "GET",
        "--url",
        f"https://graph.microsoft.com/v1.0/servicePrincipals/{sp_id}",
    )
    role_id_to_value = {
        r["id"]: r.get("value") or r.get("displayName")
        for r in sp_doc.get("appRoles", [])
    }

    enriched: list[dict[str, Any]] = []
    for r in rows:
        enriched.append(
            {
                "principal_display_name": r.get("principalDisplayName"),
                "principal_id": r.get("principalId"),
                "principal_type": r.get("principalType"),
                "role_id": r.get("appRoleId"),
                "role_value": role_id_to_value.get(r.get("appRoleId"), "?"),
                "created_at": r.get("createdDateTime"),
            }
        )
    return enriched


def _print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(no assignments)")
        return
    cols = ("principal_display_name", "principal_type", "role_value", "created_at")
    widths = {c: max(len(c), max((len(str(r.get(c, ""))) for r in rows), default=0)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print(header)
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def _print_csv(rows: list[dict[str, Any]]) -> None:
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=(
            "principal_display_name",
            "principal_id",
            "principal_type",
            "role_value",
            "role_id",
            "created_at",
        ),
    )
    writer.writeheader()
    writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="list_entra_app_role_assignments",
        description=(
            "Read-only: list who holds which AQP role on the manage API."
        ),
    )
    parser.add_argument(
        "--format",
        default="table",
        choices=("table", "json", "csv"),
    )
    parser.add_argument(
        "--apps",
        action="store_true",
        help="Also list every AQP app registration with its object id.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.apps:
        apps = _az(
            "ad",
            "app",
            "list",
            "--filter",
            "startswith(displayName, 'AQP ')",
        )
        for a in apps if isinstance(apps, list) else [apps]:
            print(f"{a['displayName']:<40}  appId={a['appId']}  objectId={a['id']}")

    sp_id = _resolve_manage_api_sp_id()
    rows = _gather_assignments(sp_id)
    if args.format == "json":
        print(json.dumps(rows, indent=2, default=str))
    elif args.format == "csv":
        _print_csv(rows)
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
