"""``aqp config`` subcommand — read / write / inspect the layered config.

Implements the canonical resolution order (global > org > team > user >
workspace > project) by leaning on :func:`aqp.config.resolve_config` and
:func:`aqp.config.set_overlay`.

Examples:

.. code-block:: shell

    # Read the effective LLM namespace for the default user
    aqp config get llm

    # Override one key at the workspace level
    aqp config set llm.deep_model gpt-5.5 --scope workspace --scope-id <wid>

    # Show effective deltas between two scopes
    aqp config diff --from user --from-id <uid> --to workspace --to-id <wid> --namespace llm

    # Drop one overlay row entirely
    aqp config clear llm --scope project --scope-id <pid>
"""
from __future__ import annotations

import json

import typer

from aqp.auth.context import RequestContext
from aqp.config import (
    DEFAULT_LAB_ID,
    DEFAULT_ORG_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_TEAM_ID,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
    clear_overlay,
    get_overlay,
    get_path,
    resolve_config,
    set_overlay,
)
from aqp.config.defaults import ALL_SCOPE_KINDS, SCOPE_GLOBAL

app = typer.Typer(no_args_is_help=True)


def _build_default_context() -> RequestContext:
    return RequestContext(
        user_id=DEFAULT_USER_ID,
        org_id=DEFAULT_ORG_ID,
        team_id=DEFAULT_TEAM_ID,
        workspace_id=DEFAULT_WORKSPACE_ID,
        project_id=DEFAULT_PROJECT_ID,
        lab_id=DEFAULT_LAB_ID,
    )


@app.command("get")
def get_cmd(
    path: str = typer.Argument(..., help="Namespace or dotted path (eg 'llm' or 'llm.deep_model')"),
    raw: bool = typer.Option(False, "--raw", help="Print the full namespace dict, not the resolved value"),
) -> None:
    """Resolve the effective value at *path* using the local-first context."""
    namespace = path.split(".", 1)[0]
    sub_path = path.split(".", 1)[1] if "." in path else ""
    cfg = resolve_config(namespace=namespace, context=_build_default_context())
    if raw or not sub_path:
        typer.echo(json.dumps(cfg, indent=2, default=str))
    else:
        value = get_path(cfg, sub_path)
        typer.echo(json.dumps(value, indent=2, default=str))


@app.command("set")
def set_cmd(
    path: str = typer.Argument(..., help="Namespace.key path (eg 'llm.deep_model')"),
    value: str = typer.Argument(..., help="JSON-encoded value (string, number, dict, list)"),
    scope: str = typer.Option(..., "--scope", help=f"One of {','.join(s for s in ALL_SCOPE_KINDS if s != SCOPE_GLOBAL)}"),
    scope_id: str = typer.Option(..., "--scope-id", help="ID of the scope (org/team/user/workspace/project/lab id)"),
    conflict: str = typer.Option("last", "--conflict", help="error | first | last"),
) -> None:
    """Write a single overlay row at the given scope."""
    namespace = path.split(".", 1)[0]
    sub_path = path.split(".", 1)[1] if "." in path else None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value

    if sub_path is None:
        if not isinstance(parsed, dict):
            typer.secho("Value must be a JSON object when no sub-path is given", fg=typer.colors.RED)
            raise typer.Exit(code=2)
        payload = parsed
    else:
        payload = _nest(sub_path, parsed)

    rid = set_overlay(scope, scope_id, namespace, payload, conflict=conflict)
    typer.echo(f"Wrote overlay row {rid}")


@app.command("clear")
def clear_cmd(
    namespace: str = typer.Argument(..., help="Namespace to drop at the given scope"),
    scope: str = typer.Option(..., "--scope"),
    scope_id: str = typer.Option(..., "--scope-id"),
) -> None:
    """Drop one overlay row entirely."""
    removed = clear_overlay(scope, scope_id, namespace)
    if removed:
        typer.echo(f"Removed overlay {scope}/{scope_id}/{namespace}")
    else:
        typer.echo(f"No overlay row at {scope}/{scope_id}/{namespace}")


@app.command("show")
def show_cmd(
    namespace: str = typer.Argument(..., help="Namespace to inspect"),
    scope: str = typer.Option(..., "--scope"),
    scope_id: str = typer.Option("", "--scope-id"),
) -> None:
    """Show the raw payload at one scope (without resolving the rest of the stack)."""
    overlay = get_overlay(scope, scope_id, namespace)
    typer.echo(json.dumps(overlay or {}, indent=2, default=str))


@app.command("diff")
def diff_cmd(
    namespace: str = typer.Option(..., "--namespace"),
    from_scope: str = typer.Option(..., "--from", help="Scope kind to baseline from"),
    from_id: str = typer.Option("", "--from-id", help="Scope id to baseline from"),
    to_scope: str = typer.Option(..., "--to", help="Scope kind to compare against"),
    to_id: str = typer.Option("", "--to-id", help="Scope id to compare against"),
) -> None:
    """Show the per-key delta between two effective configs."""
    base_ctx = _build_default_context().with_overrides(**{f"{from_scope}_id": from_id} if from_id else {})
    cmp_ctx = _build_default_context().with_overrides(**{f"{to_scope}_id": to_id} if to_id else {})
    base = resolve_config(namespace, base_ctx)
    cmp_ = resolve_config(namespace, cmp_ctx)
    diff = _flatten_diff(base, cmp_)
    typer.echo(json.dumps(diff, indent=2, default=str))


def _nest(dotted: str, leaf: object) -> dict:
    parts = dotted.split(".")
    out: dict = {}
    cur: dict = out
    for p in parts[:-1]:
        cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = leaf
    return out


def _flatten_diff(left: dict, right: dict, prefix: str = "") -> dict:
    out: dict[str, dict] = {}
    keys = set(left) | set(right)
    for k in sorted(keys):
        path = f"{prefix}.{k}" if prefix else k
        lv, rv = left.get(k, "<missing>"), right.get(k, "<missing>")
        if isinstance(lv, dict) and isinstance(rv, dict):
            out.update(_flatten_diff(lv, rv, path))
        elif lv != rv:
            out[path] = {"from": lv, "to": rv}
    return out


__all__ = ["app"]
