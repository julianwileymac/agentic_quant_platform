"""`aqp-cli auth` — login, logout, whoami, provider discovery, refresh.

Login paths (in increasing order of preference):

1. ``--token`` / ``--from-env`` — manual / CI / break-glass.
2. ``--code --redirect-uri --code-verifier`` — browser-driven PKCE
   exchange via the AQP API ``/auth/exchange`` endpoint. Used by
   the SPA-issued post-redirect handoff.
3. ``--direct --i-understand`` — emergency env-var fallback when
   neither path above is reachable. Deprecated: prefer ``--device``.
4. ``--device`` — RFC 8628 Device Authorization Grant straight to
   the configured OIDC IdP (Auth0 / Entra / generic OIDC). The
   recommended path for headless terminals.

All paths persist via :class:`aqp_cli.auth.keyring_store.KeyringStore`
when the ``[keyring]`` extra is installed (AGENTS hard rule 53). The
legacy plaintext JSON fallback remains available but is gated by the
``AQP_CLI_AUTH_ALLOW_PLAINTEXT_FALLBACK=1`` opt-in.
"""

from __future__ import annotations

import os
import webbrowser
from typing import Any

import httpx
import typer

from aqp_cli.clients import DirectAuth, MonolithClient
from aqp_cli.commands._common import exit_for_http_error
from aqp_cli.config import (
    clear_auth_state,
    get_settings,
    load_auth_state,
    resolve_access_token,
    save_auth_state,
)
from aqp_cli.ui.output import console, error, info, redact_token, render_json, warn

app = typer.Typer(no_args_is_help=True, help="Authenticate to AQP.")


def _persist_token_payload(payload: dict[str, Any]) -> None:
    """Persist tokens to BOTH the OS keyring (when available) AND the
    legacy JSON cache.

    Dual-write during the one-release backward-compat window so users
    on older `aqp-cli` versions keep working when they roll back a
    point release. After the next minor we drop the JSON write.
    """
    settings = get_settings()
    state = load_auth_state(settings)
    state.update(payload)
    save_auth_state(settings, state)
    access_token = str(state.get("access_token") or "")
    refresh_token = state.get("refresh_token")
    id_token = state.get("id_token")
    expires_at = state.get("expires_at")
    try:
        from aqp_cli.auth.keyring_store import KeyringStore, KeyringStoreError

        store = KeyringStore.for_default()
        if store.is_available():
            try:
                store.set_tokens(
                    access_token=access_token or None,
                    refresh_token=str(refresh_token) if refresh_token else None,
                    id_token=str(id_token) if id_token else None,
                    expires_at=float(expires_at) if expires_at else None,
                    metadata={
                        "source": str(payload.get("source") or state.get("source") or ""),
                    },
                )
            except KeyringStoreError as exc:
                warn(f"keyring store unavailable: {exc}; falling back to plaintext JSON")
        else:
            warn(
                "OS keyring not available (install the `keyring` extra: "
                "`pip install aqp-cli[keyring]`); using legacy plaintext JSON cache."
            )
    except Exception:
        # Never block login on a keyring failure — the legacy JSON
        # write above is sufficient for the CLI to function.
        pass
    console.print(f"[green]logged in[/green] access_token={redact_token(access_token)}")


@app.command("login")
def login(
    token: str = typer.Option("", "--token", help="Provide an access token directly."),
    from_env: bool = typer.Option(
        False,
        "--from-env",
        help="Read access token from AQP_ACCESS_TOKEN / AQP_CP_TOKEN.",
    ),
    code: str = typer.Option("", "--code", help="Authorization code for /auth/exchange."),
    redirect_uri: str = typer.Option(
        "", "--redirect-uri", help="Redirect URI used during authorization."
    ),
    code_verifier: str = typer.Option("", "--code-verifier", help="PKCE code verifier."),
    device: bool = typer.Option(
        False,
        "--device",
        help=(
            "Use the OAuth Device Authorization Grant (RFC 8628). The "
            "CLI prints a URL + user code; open the URL on any device "
            "(same workstation, phone, separate machine) to approve. "
            "Recommended for headless servers."
        ),
    ),
    domain: str = typer.Option(
        "",
        "--domain",
        envvar="AQP_CLI_OIDC_DOMAIN",
        help="OIDC tenant domain (auto-loaded from /auth/config when omitted).",
    ),
    client_id: str = typer.Option(
        "",
        "--client-id",
        envvar="AQP_CLI_OIDC_CLIENT_ID",
        help="Native OAuth client ID (auto-loaded from /auth/config when omitted).",
    ),
    audience: str = typer.Option(
        "",
        "--audience",
        envvar="AQP_CLI_OIDC_AUDIENCE",
        help="API audience (auto-loaded from /auth/config when omitted).",
    ),
    organization: str = typer.Option(
        "",
        "--organization",
        envvar="AQP_CLI_OIDC_ORGANIZATION",
        help="Auth0 Organization id (B2B) — routes via Home Realm Discovery.",
    ),
    scope: str = typer.Option(
        "openid profile email offline_access",
        "--scope",
        help="Requested OAuth scopes (offline_access is required for refresh).",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open-browser/--no-open-browser",
        help="Attempt to launch the verification URL in the default browser.",
    ),
    direct: bool = typer.Option(
        False,
        "--direct",
        help="DEPRECATED: env-var fallback. Use --device or --from-env instead.",
    ),
    i_understand: bool = typer.Option(
        False,
        "--i-understand",
        help="Required acknowledgement when using --direct.",
    ),
) -> None:
    """Authenticate and persist an access token (keyring-first; legacy JSON fallback)."""
    settings = get_settings()

    if direct and not i_understand:
        error("--direct requires --i-understand.")
        raise typer.Exit(code=2)

    if token:
        _persist_token_payload({"access_token": token.strip(), "source": "manual"})
        return

    if from_env:
        env_token = (
            os.environ.get("AQP_ACCESS_TOKEN") or os.environ.get("AQP_CP_TOKEN") or ""
        ).strip()
        if not env_token:
            error("No token found in AQP_ACCESS_TOKEN or AQP_CP_TOKEN.")
            raise typer.Exit(code=2)
        _persist_token_payload({"access_token": env_token, "source": "env"})
        return

    if direct:
        warn("--direct is deprecated; use --device for a real RFC 8628 flow.")
        fallback = DirectAuth().device_code_login()
        if not fallback:
            error("Direct mode could not resolve a token from environment.")
            raise typer.Exit(code=1)
        _persist_token_payload({"access_token": fallback, "source": "direct-env"})
        return

    if device:
        _device_login(
            settings,
            domain=domain.strip(),
            client_id=client_id.strip(),
            audience=audience.strip(),
            organization=organization.strip() or None,
            scope=scope.strip(),
            open_browser=open_browser,
        )
        return

    if code and redirect_uri:
        client = MonolithClient(settings.api_url, settings.http_timeout_seconds)
        try:
            payload = client.request(
                "POST",
                "/auth/exchange",
                json_body={
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": code_verifier or None,
                },
            )
        except httpx.HTTPStatusError as exc:
            exit_for_http_error(exc)
        finally:
            client.close()

        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
            error("Token exchange did not return an access_token.")
            raise typer.Exit(code=1)
        _persist_token_payload(
            {
                "access_token": payload["access_token"],
                "refresh_token": str(payload.get("refresh_token") or ""),
                "id_token": str(payload.get("id_token") or ""),
                "source": "exchange",
            }
        )
        return

    login_url = f"{settings.api_url.rstrip('/')}/auth/login"
    info("No token/code/device flow specified. Opening browser login URL.")
    info("(For headless terminals, prefer `aqp-cli auth login --device`.)")
    try:
        webbrowser.open(login_url)
    except Exception:
        warn("Could not open a browser automatically.")
    console.print(f"[cyan]Open[/cyan] {login_url}")
    console.print(
        "After authorization, run `aqp-cli auth login --code <code> --redirect-uri <uri> "
        "[--code-verifier <verifier>]` or pass `--token`."
    )
    raise typer.Exit(code=1)


def _device_login(
    settings: Any,
    *,
    domain: str,
    client_id: str,
    audience: str,
    organization: str | None,
    scope: str,
    open_browser: bool,
) -> None:
    """Drive the RFC 8628 Device Authorization Grant.

    When ``--domain`` / ``--client-id`` / ``--audience`` are omitted,
    the CLI fetches them from the AQP API's ``/auth/config`` endpoint
    so operators don't have to memorise tenant ids.
    """
    try:
        from aqp_cli.auth.device_flow import (
            DeviceFlowClient,
            DeviceFlowError,
        )
    except ImportError as exc:
        error(f"Device flow unavailable: {exc}")
        raise typer.Exit(code=1) from exc

    domain, client_id, audience = _resolve_oidc_config(
        settings,
        domain=domain,
        client_id=client_id,
        audience=audience,
    )
    if not domain or not client_id:
        error(
            "Device flow requires --domain + --client-id (or the AQP API "
            "must expose them via /auth/config)."
        )
        raise typer.Exit(code=2)

    client = DeviceFlowClient(
        domain=domain,
        client_id=client_id,
        audience=audience or None,
    )
    try:
        tokens = client.login(
            scope=scope,
            organization=organization,
            open_browser=open_browser,
        )
    except DeviceFlowError as exc:
        error(f"Device flow failed ({exc.code}): {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()

    _persist_token_payload(
        {
            "access_token": tokens.access_token,
            "refresh_token": str(tokens.refresh_token or ""),
            "id_token": str(tokens.id_token or ""),
            "expires_at": tokens.expires_at,
            "source": "device_flow",
        }
    )


def _resolve_oidc_config(
    settings: Any,
    *,
    domain: str,
    client_id: str,
    audience: str,
) -> tuple[str, str, str]:
    """Best-effort fetch of OIDC config from the AQP API.

    Falls back gracefully — if `/auth/config` is unreachable or
    doesn't carry the fields, the caller-supplied values win (or
    the function returns empties so the caller can complain).
    """
    if domain and client_id and audience:
        return domain, client_id, audience
    try:
        client = MonolithClient(settings.api_url, settings.http_timeout_seconds)
    except Exception:
        return domain, client_id, audience
    try:
        payload = client.request("GET", "/auth/config")
    except Exception:
        return domain, client_id, audience
    finally:
        try:
            client.close()
        except Exception:
            pass
    if isinstance(payload, dict):
        domain = domain or str(
            payload.get("cli_oidc_domain")
            or payload.get("oidc_domain")
            or payload.get("issuer_domain")
            or ""
        ).strip()
        client_id = client_id or str(
            payload.get("cli_oidc_client_id")
            or payload.get("oidc_client_id")
            or ""
        ).strip()
        audience = audience or str(
            payload.get("oidc_audience") or payload.get("audience") or ""
        ).strip()
    return domain, client_id, audience


@app.command("diagnose")
def diagnose() -> None:
    """Print credential-store diagnostics. NEVER prints token values."""
    try:
        from aqp_cli.auth.keyring_store import diagnose as _diagnose
    except ImportError:
        render_json({"backend": "unavailable", "reason": "keyring extra not installed"})
        return
    render_json(_diagnose())


@app.command("whoami")
def whoami() -> None:
    """Show the current authenticated principal."""
    settings = get_settings()
    token = resolve_access_token(settings)
    if not token:
        console.print("[yellow]Not logged in.[/yellow]")
        raise typer.Exit(code=1)

    client = MonolithClient(settings.api_url, settings.http_timeout_seconds, token)
    try:
        profile = client.request("GET", "/auth/whoami")
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()

    render_json(profile)


@app.command("providers")
def providers() -> None:
    """List registered identity providers from the management BFF route."""
    settings = get_settings()
    client = MonolithClient(settings.api_url, settings.http_timeout_seconds)
    try:
        payload = client.request("GET", "/auth/providers")
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    render_json(payload)


@app.command("refresh")
def refresh(
    refresh_token: str = typer.Option("", "--refresh-token", help="Refresh token override."),
) -> None:
    """Exchange a refresh token for a new access token."""
    settings = get_settings()
    state = load_auth_state(settings)
    token = refresh_token.strip() or str(state.get("refresh_token") or "").strip()
    if not token:
        error("No refresh token available. Pass --refresh-token or login via --code exchange.")
        raise typer.Exit(code=2)
    client = MonolithClient(settings.api_url, settings.http_timeout_seconds)
    try:
        payload = client.request("POST", "/auth/refresh", json_body={"refresh_token": token})
    except httpx.HTTPStatusError as exc:
        exit_for_http_error(exc)
    finally:
        client.close()
    if not isinstance(payload, dict) or not payload.get("access_token"):
        error("Refresh response missing access_token.")
        raise typer.Exit(code=1)
    _persist_token_payload(
        {
            "access_token": str(payload.get("access_token") or ""),
            "refresh_token": str(payload.get("refresh_token") or token),
            "id_token": str(payload.get("id_token") or state.get("id_token") or ""),
            "source": "refresh",
        }
    )


@app.command("logout")
def logout() -> None:
    """Clear the local token cache (keyring + JSON) and attempt backend logout."""
    settings = get_settings()
    state = load_auth_state(settings)
    token = str(state.get("access_token") or "") or resolve_access_token(settings)
    if token:
        client = MonolithClient(settings.api_url, settings.http_timeout_seconds, token)
        try:
            client.request("POST", "/auth/logout")
        except Exception:
            warn("Backend logout request failed; local session will still be cleared.")
        finally:
            client.close()
    clear_auth_state(settings)
    try:
        from aqp_cli.auth.keyring_store import KeyringStore

        store = KeyringStore.for_default()
        store.clear()
    except Exception:
        # Best-effort — clearing the JSON file is sufficient even if
        # the keyring backend rejects the delete.
        pass
    console.print("[green]logged out[/green]")
