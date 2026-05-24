"""``aqp ratelimit`` CLI subcommands.

Verbs:

- ``aqp ratelimit status`` — print the calling user's bucket state
  (optionally filtered by ``--service`` / ``--key-id``); supports
  ``--output table|json|yaml`` for scriptability.
- ``aqp ratelimit policies`` — list active policies for the
  EntityPicker dropdown.
"""
from __future__ import annotations

import json
from typing import Any

import typer

app = typer.Typer(
    name="ratelimit",
    help="Inspect per-(user, service, key_id) rate-limit state",
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
def status(
    service: str | None = typer.Option(None, help="Filter to one service"),
    key_id: str | None = typer.Option(None, help="Filter to one key label"),
    output: str = typer.Option(
        "table",
        case_sensitive=False,
        help="Output format: table | json | yaml",
    ),
) -> None:
    """Show bucket state for the calling user."""
    try:
        from aqp_ratelimit.cli._common import resolve_user_id_from_env

        user_id = resolve_user_id_from_env()
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)

    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_ratelimit import RateLimitKey
        from aqp_ratelimit import get_ratelimit_client

        client = get_ratelimit_client()
        with get_session() as session:
            q = session.query(RateLimitKey).filter(
                RateLimitKey.owner_user_id == user_id,
                RateLimitKey.revoked_at.is_(None),
            )
            if service:
                q = q.filter(RateLimitKey.service == service)
            if key_id:
                q = q.filter(RateLimitKey.label == key_id)
            rows = q.all()
        out = []
        for row in rows:
            decision = client.status(
                user_id=user_id,
                service=row.service,
                key_id=row.label,
            )
            out.append(
                {
                    "service": row.service,
                    "key_id": row.label,
                    "remaining": round(decision.remaining, 2),
                    "capacity": int(decision.capacity),
                    "refill_rps": round(decision.refill_rate, 3),
                    "allow": decision.allow,
                }
            )
        _emit(out, output)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)


@app.command()
def policies(
    service: str | None = typer.Option(None, help="Filter to one service"),
    tier: str | None = typer.Option(None, help="Filter to one tier"),
    output: str = typer.Option("table", case_sensitive=False),
) -> None:
    """List active rate-limit policies."""
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_ratelimit import RateLimitPolicy

        with get_session() as session:
            q = session.query(RateLimitPolicy).filter(
                RateLimitPolicy.is_active.is_(True)
            )
            if service:
                q = q.filter(RateLimitPolicy.service == service)
            if tier:
                q = q.filter(RateLimitPolicy.tier == tier)
            rows = q.order_by(RateLimitPolicy.service.asc()).all()
        out = [
            {
                "policy_id": row.id,
                "service": row.service,
                "tier": row.tier,
                "capacity": int(row.capacity),
                "refill_rps": round(float(row.refill_rate), 3),
                "window_ms": int(row.window_ms or 60_000),
            }
            for row in rows
        ]
        _emit(out, output)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1)


__all__ = ["app"]
