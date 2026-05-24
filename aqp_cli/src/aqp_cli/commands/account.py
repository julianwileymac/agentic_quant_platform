"""`aqp-cli account` — profile, sessions, MFA, connected-account operations."""

from __future__ import annotations

import httpx
import typer

from aqp_cli.commands._common import exit_for_http_error, monolith_client
from aqp_cli.ui.output import render_json

app = typer.Typer(no_args_is_help=True, help="General account management (`/me/*`).")
sessions_app = typer.Typer(no_args_is_help=True, help="Session lifecycle commands.")
mfa_app = typer.Typer(no_args_is_help=True, help="MFA enrollment and factor management.")
connections_app = typer.Typer(no_args_is_help=True, help="Connected account commands.")

app.add_typer(sessions_app, name="sessions")
app.add_typer(mfa_app, name="mfa")
app.add_typer(connections_app, name="connections")


@app.command("profile")
def profile() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("GET", "/me"))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("update")
def update(
    display_name: str = typer.Option("", "--display-name"),
    avatar_url: str = typer.Option("", "--avatar-url"),
    picture: str = typer.Option("", "--picture"),
) -> None:
    payload: dict[str, str] = {}
    if display_name:
        payload["display_name"] = display_name
    if avatar_url:
        payload["avatar_url"] = avatar_url
    if picture:
        payload["picture"] = picture
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("PATCH", "/me", json_body=payload))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("change-password")
def change_password(return_url: str = typer.Option(..., "--return-url")) -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(
            client.request("POST", "/me/change-password", json_body={"return_url": return_url})
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("audit")
def audit(
    page: int = typer.Option(0, "--page", min=0),
    per_page: int = typer.Option(50, "--per-page", min=1, max=200),
) -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("GET", "/me/audit", params={"page": page, "per_page": per_page}))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@app.command("delete")
def delete_account(confirm_email: str = typer.Option(..., "--confirm-email")) -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(
            client.request(
                "DELETE",
                "/me",
                headers={"X-AQP-Confirm-Email": confirm_email},
            )
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@sessions_app.command("list")
def sessions_list() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("GET", "/me/sessions"))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@sessions_app.command("revoke")
def sessions_revoke(session_id: str = typer.Argument(...)) -> None:
    client = monolith_client(require_token=True)
    try:
        client.request("DELETE", f"/me/sessions/{session_id}")
        render_json({"status": "ok", "revoked_session_id": session_id})
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@sessions_app.command("revoke-all")
def sessions_revoke_all() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("DELETE", "/me/sessions"))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@mfa_app.command("list")
def mfa_list() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("GET", "/me/mfa/factors"))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@mfa_app.command("enroll")
def mfa_enroll(
    factor: str = typer.Option(
        ..., "--factor", help="totp|sms|webauthn-roaming|webauthn-platform|push"
    ),
    return_url: str = typer.Option("", "--return-url"),
) -> None:
    payload = {"factor": factor}
    if return_url:
        payload["return_url"] = return_url
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("POST", "/me/mfa/enroll", json_body=payload))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@mfa_app.command("remove")
def mfa_remove(factor_id: str = typer.Argument(...)) -> None:
    client = monolith_client(require_token=True)
    try:
        client.request("DELETE", f"/me/mfa/factors/{factor_id}")
        render_json({"status": "ok", "removed_factor_id": factor_id})
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@connections_app.command("list")
def connections_list() -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(client.request("GET", "/me/connected-accounts"))
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@connections_app.command("link")
def connections_link(secondary_jwt: str = typer.Option(..., "--secondary-jwt")) -> None:
    client = monolith_client(require_token=True)
    try:
        render_json(
            client.request(
                "POST",
                "/me/connected-accounts/link",
                json_body={"secondary_jwt": secondary_jwt},
            )
        )
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()


@connections_app.command("unlink")
def connections_unlink(
    secondary_user_id: str = typer.Argument(...),
    provider: str = typer.Option(..., "--provider"),
) -> None:
    client = monolith_client(require_token=True)
    try:
        client.request(
            "DELETE",
            f"/me/connected-accounts/{secondary_user_id}",
            json_body={"provider": provider},
        )
        render_json({"status": "ok", "provider": provider, "secondary_user_id": secondary_user_id})
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
