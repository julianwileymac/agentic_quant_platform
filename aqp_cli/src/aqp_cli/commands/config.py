"""`aqp-cli config` — layered config read/write over `/configs/*` routes."""

from __future__ import annotations

import json

import httpx
import typer

from aqp_cli.commands._common import exit_for_http_error, monolith_client
from aqp_cli.ui.output import render_json

app = typer.Typer(no_args_is_help=True, help="Layered config inspection/mutation.")


def _nest(path: str, value: object) -> dict[str, object]:
    out: dict[str, object] = {}
    cursor: dict[str, object] = out
    parts = path.split(".")
    for part in parts[:-1]:
        cursor[part] = {}
        cursor = cursor[part]  # type: ignore[assignment]
    cursor[parts[-1]] = value
    return out


def _extract_path(payload: object, dotted: str) -> object:
    current = payload
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _flatten_diff(
    left: dict[str, object], right: dict[str, object], prefix: str = ""
) -> dict[str, object]:
    out: dict[str, object] = {}
    keys = set(left) | set(right)
    for key in sorted(keys):
        dotted = f"{prefix}.{key}" if prefix else key
        left_val = left.get(key, "<missing>")
        right_val = right.get(key, "<missing>")
        if isinstance(left_val, dict) and isinstance(right_val, dict):
            out.update(_flatten_diff(left_val, right_val, dotted))
        elif left_val != right_val:
            out[dotted] = {"from": left_val, "to": right_val}
    return out


@app.command("get")
def get_cmd(
    path: str = typer.Argument(..., help="Namespace or dotted path (e.g. llm.deep_model)."),
) -> None:
    namespace = path.split(".", 1)[0]
    sub_path = path.split(".", 1)[1] if "." in path else ""
    client = monolith_client(require_token=True)
    try:
        payload = client.request("GET", "/configs/effective", params={"namespace": namespace})
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(_extract_path(payload, sub_path) if sub_path else payload)


@app.command("set")
def set_cmd(
    path: str = typer.Argument(..., help="Namespace.key path (e.g. llm.deep_model)"),
    value: str = typer.Argument(..., help="JSON-encoded value or plain string."),
    scope: str = typer.Option(..., "--scope"),
    scope_id: str = typer.Option(..., "--scope-id"),
    conflict: str = typer.Option("last", "--conflict"),
) -> None:
    namespace = path.split(".", 1)[0]
    sub_path = path.split(".", 1)[1] if "." in path else ""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    payload = parsed if not sub_path else _nest(sub_path, parsed)
    client = monolith_client(require_token=True)
    try:
        response = client.request(
            "PUT",
            f"/configs/{scope}/{scope_id}/{namespace}",
            json_body={"payload": payload, "conflict": conflict},
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(response)


@app.command("clear")
def clear_cmd(
    namespace: str = typer.Argument(...),
    scope: str = typer.Option(..., "--scope"),
    scope_id: str = typer.Option(..., "--scope-id"),
) -> None:
    client = monolith_client(require_token=True)
    try:
        client.request("DELETE", f"/configs/{scope}/{scope_id}/{namespace}")
        render_json({"status": "ok", "scope": scope, "scope_id": scope_id, "namespace": namespace})
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("show")
def show_cmd(
    namespace: str = typer.Argument(...),
    scope: str = typer.Option(..., "--scope"),
    scope_id: str = typer.Option("", "--scope-id"),
) -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("GET", f"/configs/{scope}/{scope_id}/{namespace}"))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("diff")
def diff_cmd(
    namespace: str = typer.Option(..., "--namespace"),
    from_scope: str = typer.Option(..., "--from"),
    from_id: str = typer.Option("", "--from-id"),
    to_scope: str = typer.Option(..., "--to"),
    to_id: str = typer.Option("", "--to-id"),
) -> None:
    client = monolith_client(require_token=True)
    try:
        left = client.request("GET", f"/configs/{from_scope}/{from_id}/{namespace}")
        right = client.request("GET", f"/configs/{to_scope}/{to_id}/{namespace}")
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    if not isinstance(left, dict) or not isinstance(right, dict):
        render_json({"from": left, "to": right})
        return
    render_json(_flatten_diff(left, right))
