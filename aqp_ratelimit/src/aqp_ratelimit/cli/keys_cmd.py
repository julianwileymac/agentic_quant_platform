"""``aqp keys`` CLI subcommands for per-user vendor key lifecycle.

Verbs:

- ``aqp keys mint`` — register a new vendor key binding (also creates
  a matching policy if ``--rps`` is provided).
- ``aqp keys list`` — enumerate the calling user's keys.
- ``aqp keys rotate`` — generate a new label + revoke the previous
  (the actual secret rotation happens at the Vault path).
- ``aqp keys revoke`` — mark a key revoked.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

import typer

app = typer.Typer(
    name="keys",
    help="Lifecycle management for per-user vendor API keys",
    no_args_is_help=True,
)


def _emit(rows: list[dict[str, Any]], output: str) -> None:
    if output == "json":
        typer.echo(json.dumps(rows, indent=2, default=str))
        return
    if output == "yaml":
        try:
            import yaml

            typer.echo(yaml.safe_dump(rows, sort_keys=False))
        except ImportError:
            typer.echo(json.dumps(rows, indent=2, default=str))
        return
    if not rows:
        typer.echo("no rows")
        return
    headers = list(rows[0].keys())
    typer.echo("  ".join(h.upper() for h in headers))
    for row in rows:
        typer.echo("  ".join(str(row.get(h, "")) for h in headers))


@app.command()
def mint(
    service: str = typer.Option(..., help="Vendor service slug (e.g. polygon)"),
    label: str = typer.Option("primary", help="Per-user label"),
    rps: float | None = typer.Option(
        None, help="Tokens per second; defaults to existing policy"
    ),
    burst: int | None = typer.Option(
        None, help="Bucket capacity; defaults to rps * 60"
    ),
    ttl: str | None = typer.Option(
        None,
        help="Time to live, e.g. 30d / 90d / 365d. Leave empty for no expiry.",
    ),
    vault_path: str | None = typer.Option(
        None,
        help="Vault path holding the secret. Defaults to the per-user OAuth path.",
    ),
) -> None:
    """Mint a new per-user vendor key binding."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitKey, RateLimitPolicy
    from aqp_ratelimit.cli._common import resolve_user_id_from_env

    user_id = resolve_user_id_from_env()
    ttl_days = _parse_ttl_days(ttl) if ttl else None
    with get_session() as session:
        policy = (
            session.query(RateLimitPolicy)
            .filter(
                RateLimitPolicy.service == service,
                RateLimitPolicy.is_active.is_(True),
            )
            .first()
        )
        if rps is not None:
            capacity = int(burst or max(1, int(rps * 60)))
            policy = RateLimitPolicy(
                id=str(uuid.uuid4()),
                owner_user_id=user_id,
                service=service,
                tier="custom",
                capacity=capacity,
                refill_rate=float(rps),
                refill_interval_ms=1000,
                window_ms=60_000,
                notes=f"auto-created by aqp keys mint by {user_id}",
                is_active=True,
            )
            session.add(policy)
            session.flush()
        expires_at = (
            datetime.utcnow() + timedelta(days=ttl_days) if ttl_days else None
        )
        row = RateLimitKey(
            id=str(uuid.uuid4()),
            owner_user_id=user_id,
            service=service,
            policy_id=policy.id if policy else None,
            label=label,
            vault_path=vault_path
            or f"secret/data/users/{user_id}/services/{service}",
            issued_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        session.add(row)
        session.commit()
        typer.echo(f"minted key {row.id} (service={service}, label={label})")


@app.command(name="list")
def list_keys(
    include_revoked: bool = typer.Option(False, "--include-revoked"),
    output: str = typer.Option("table", case_sensitive=False),
) -> None:
    """List the calling user's vendor keys."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitKey
    from aqp_ratelimit.cli._common import resolve_user_id_from_env

    user_id = resolve_user_id_from_env()
    with get_session() as session:
        q = session.query(RateLimitKey).filter(
            RateLimitKey.owner_user_id == user_id
        )
        if not include_revoked:
            q = q.filter(RateLimitKey.revoked_at.is_(None))
        rows = q.order_by(RateLimitKey.issued_at.desc()).all()
    _emit(
        [
            {
                "key_id": row.id,
                "service": row.service,
                "label": row.label,
                "issued_at": row.issued_at,
                "expires_at": row.expires_at,
                "revoked_at": row.revoked_at,
            }
            for row in rows
        ],
        output,
    )


@app.command()
def rotate(
    key_id: str = typer.Option(..., help="Existing key id to rotate"),
    new_label: str = typer.Option(..., help="Label for the new key binding"),
) -> None:
    """Mint a new key with ``new_label`` and revoke ``key_id``."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitKey
    from aqp_ratelimit.cli._common import resolve_user_id_from_env

    user_id = resolve_user_id_from_env()
    with get_session() as session:
        old = session.get(RateLimitKey, key_id)
        if old is None or old.owner_user_id != user_id:
            raise typer.BadParameter(f"key {key_id!r} not found for this user")
        new_row = RateLimitKey(
            id=str(uuid.uuid4()),
            owner_user_id=user_id,
            service=old.service,
            policy_id=old.policy_id,
            label=new_label,
            vault_path=old.vault_path,
            issued_at=datetime.utcnow(),
            expires_at=old.expires_at,
        )
        old.revoked_at = datetime.utcnow()
        old.revoked_by_user_id = user_id
        session.add(new_row)
        session.commit()
        typer.echo(
            f"rotated: revoked {old.id}, new key {new_row.id} ({old.service}/{new_label})"
        )


@app.command()
def revoke(
    key_id: str = typer.Option(..., help="Key id to revoke"),
) -> None:
    """Revoke a per-user vendor key."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_ratelimit import RateLimitKey
    from aqp_ratelimit.cli._common import resolve_user_id_from_env

    user_id = resolve_user_id_from_env()
    with get_session() as session:
        row = session.get(RateLimitKey, key_id)
        if row is None or row.owner_user_id != user_id:
            raise typer.BadParameter(f"key {key_id!r} not found")
        if row.revoked_at is None:
            row.revoked_at = datetime.utcnow()
            row.revoked_by_user_id = user_id
            session.commit()
        typer.echo(f"revoked {row.id}")


def _parse_ttl_days(ttl: str) -> int:
    if ttl.endswith("d"):
        return int(ttl[:-1])
    if ttl.endswith("y"):
        return int(ttl[:-1]) * 365
    if ttl.endswith("m"):
        return int(ttl[:-1]) * 30
    return int(ttl)


__all__ = ["app"]
