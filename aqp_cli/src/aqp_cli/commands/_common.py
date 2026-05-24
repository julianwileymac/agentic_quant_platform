"""Shared helpers for command modules."""

from __future__ import annotations

from typing import Any

import httpx
import typer

from aqp_cli.clients import ControlPlaneClient, MonolithClient
from aqp_cli.config import get_settings, resolve_access_token
from aqp_cli.ui.output import error


def settings_and_token() -> tuple[Any, str]:
    settings = get_settings()
    token = resolve_access_token(settings)
    return settings, token


def monolith_client(require_token: bool = False) -> MonolithClient:
    settings, token = settings_and_token()
    if require_token and not token:
        error("No access token found. Run `aqp-cli auth login` first.")
        raise typer.Exit(code=2)
    return MonolithClient(settings.api_url, settings.http_timeout_seconds, token)


def control_plane_client(require_token: bool = False) -> ControlPlaneClient:
    settings, token = settings_and_token()
    if require_token and not token:
        error("No access token found. Run `aqp-cli auth login` first.")
        raise typer.Exit(code=2)
    return ControlPlaneClient(settings.control_plane_url, settings.http_timeout_seconds, token)


def exit_for_http_error(exc: httpx.HTTPStatusError) -> None:
    response = exc.response
    code = response.status_code
    try:
        payload = response.json()
    except Exception:
        payload = response.text
    error(f"{code} {response.request.method} {response.request.url}")
    if payload:
        typer.echo(payload)
    raise typer.Exit(code=1)
