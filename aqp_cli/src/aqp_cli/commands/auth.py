"""`aqp-cli auth` — login, logout, whoami.

Default path is brokered through the control plane (AQP rule 27). The
``--direct`` flag is an escape hatch that requires an explicit
``--i-understand`` acknowledgement and falls back to direct OIDC against
the identity provider configured on disk.
"""
from __future__ import annotations

import typer

from aqp_cli.clients.control_plane import ControlPlaneClient
from aqp_cli.clients.direct import DirectAuth
from aqp_cli.config import get_settings
from aqp_cli.ui.output import console, error, info, redact_token

app = typer.Typer(no_args_is_help=True, help="Authenticate to AQP.")


@app.command("login")
def login(
    direct: bool = typer.Option(False, "--direct", help="Use direct OIDC instead of the control plane."),
    i_understand: bool = typer.Option(
        False, "--i-understand", help="Required acknowledgement when using --direct."
    ),
) -> None:
    """Start a login flow. Default: device-code via the control plane."""
    settings = get_settings()
    if direct and not i_understand:
        error("--direct requires --i-understand (rule 27: identity goes through the control plane).")
        raise typer.Exit(code=2)

    if direct:
        info(f"Direct OIDC against the IdP configured for {settings.api_url} (stub)")
        token = DirectAuth().device_code_login()
    else:
        info(f"Brokered login via {settings.control_plane_url} (stub)")
        cp = ControlPlaneClient(settings.control_plane_url, settings.http_timeout_seconds)
        token = cp.device_code_login()

    if token is None:
        error("login flow did not return a token (stub)")
        raise typer.Exit(code=1)
    console.print(f"[green]logged in[/green] access_token={redact_token(token)}")


@app.command("whoami")
def whoami() -> None:
    """Show the current authenticated principal."""
    settings = get_settings()
    cp = ControlPlaneClient(settings.control_plane_url, settings.http_timeout_seconds)
    profile = cp.whoami()
    if profile is None:
        console.print("[yellow]Not logged in.[/yellow]")
        return
    console.print(profile)


@app.command("logout")
def logout() -> None:
    """Clear the local token cache."""
    settings = get_settings()
    info(f"Would clear credentials under {settings.credentials_dir} (stub)")
    console.print("[green]logged out (stub).[/green]")
