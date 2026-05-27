"""Seed the AQP staff Entra tenant in ``entra_tenant_links``.

Workstream "Entra internal tenant"
(docs/plans/entra-internal-tenant-rollout.md). After the
``aqp_entra_directory`` Terraform stack lands the staff app, this
script inserts (or updates) the canonical row in
``entra_tenant_links`` with ``meta.kind = 'internal'``.

The insert is idempotent:

- If no row exists for ``settings.auth_msal_internal_tenant_id``, it
  creates one in ``status='active'`` with ``meta.kind='internal'``.
- If a row exists with the same tenant id but ``meta.kind`` is unset
  or different, it updates ``meta`` and bumps ``updated_at``.
- ``--revoke`` flips the row to ``status='revoked'`` (Phase rollback).
- ``--dry-run`` prints what would happen without writing.

The script DOES NOT mutate Vault — the Terraform module's outputs
(staff_app_client_id, manage_api_identifier_uri) carry the runtime
values; the operator pastes them into Vault separately as documented
in the entra-rotate-secrets runbook.

Usage:

    # Inspect current state.
    python scripts/identity/seed_entra_internal_tenant.py --dry-run

    # Apply (idempotent).
    python scripts/identity/seed_entra_internal_tenant.py --apply

    # Phase rollback.
    python scripts/identity/seed_entra_internal_tenant.py --revoke
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger("seed_entra_internal_tenant")


def _load_settings():
    from aqp.config import settings  # type: ignore[import-not-found]

    tenant_id = (settings.auth_msal_internal_tenant_id or "").strip()
    domain = (settings.auth_msal_internal_tenant_domain or "").strip()
    display_name = (settings.auth_msal_internal_display_name or "").strip()
    if not tenant_id:
        raise SystemExit(
            "AQP_AUTH_MSAL_INTERNAL_TENANT_ID is empty; nothing to seed.\n"
            "Set it in the environment or .env from the Terraform output "
            "``entra_tenant_id``."
        )
    return tenant_id, domain, display_name


def _operate(*, apply: bool, revoke: bool) -> int:
    tenant_id, primary_domain, display_name = _load_settings()
    logger.info(
        "Target tenant_id=%s domain=%s display_name=%r",
        tenant_id,
        primary_domain,
        display_name,
    )

    from sqlalchemy import select, update  # type: ignore[import-not-found]

    from aqp.persistence.db import get_session  # type: ignore[import-not-found]
    from aqp.persistence.models_terraform import EntraTenantLink  # type: ignore[import-not-found]

    with get_session() as session:
        existing = session.execute(
            select(EntraTenantLink).where(
                EntraTenantLink.entra_tenant_id == tenant_id
            )
        ).scalar_one_or_none()

        target_status = "revoked" if revoke else "active"
        target_kind = "internal"
        meta = {"kind": target_kind, "managed_by": "aqp_entra_directory"}

        if existing is None:
            logger.info(
                "no existing row; would INSERT %s tenant=%s",
                "(dry-run) " if not apply else "",
                tenant_id,
            )
            if not apply:
                return 0
            row = EntraTenantLink(
                entra_tenant_id=tenant_id,
                primary_domain=primary_domain or None,
                display_name=display_name or None,
                status=target_status,
                meta=meta,
            )
            session.add(row)
            session.commit()
            logger.info("INSERTED tenant_id=%s id=%s", tenant_id, row.id)
            return 0

        # Existing row — decide if any field needs an update.
        merged_meta = dict(existing.meta or {})
        merged_meta.update(meta)
        diffs: dict[str, tuple] = {}
        if existing.status != target_status:
            diffs["status"] = (existing.status, target_status)
        if (existing.primary_domain or "") != primary_domain:
            diffs["primary_domain"] = (existing.primary_domain, primary_domain)
        if (existing.display_name or "") != display_name:
            diffs["display_name"] = (existing.display_name, display_name)
        if (existing.meta or {}).get("kind") != target_kind:
            diffs["meta.kind"] = ((existing.meta or {}).get("kind"), target_kind)

        if not diffs:
            logger.info("EXISTING row matches target; no-op.")
            return 0

        logger.info(
            "EXISTING row needs update %s: %s",
            "(dry-run)" if not apply else "",
            json.dumps(
                {k: {"from": v[0], "to": v[1]} for k, v in diffs.items()},
                default=str,
            ),
        )
        if not apply:
            return 0

        session.execute(
            update(EntraTenantLink)
            .where(EntraTenantLink.id == existing.id)
            .values(
                status=target_status,
                primary_domain=primary_domain or existing.primary_domain,
                display_name=display_name or existing.display_name,
                meta=merged_meta,
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        logger.info("UPDATED tenant_id=%s id=%s", tenant_id, existing.id)
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed_entra_internal_tenant",
        description=(
            "Idempotently upsert the AQP staff Entra tenant in "
            "entra_tenant_links with meta.kind='internal'."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--apply",
        action="store_true",
        help="Persist the change. Default mode is dry-run.",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen without writing (default).",
    )
    group.add_argument(
        "--revoke",
        action="store_true",
        help="Flip the row to status='revoked'. Phase rollback path.",
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

    apply = args.apply or args.revoke
    revoke = args.revoke
    return _operate(apply=apply, revoke=revoke)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
