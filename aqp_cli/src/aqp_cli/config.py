"""CLI configuration + local state helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AqpCliSettings(BaseSettings):
    """Top-level operator CLI settings."""

    model_config = SettingsConfigDict(
        env_prefix="AQP_CLI_",
        env_file=None,
        extra="ignore",
    )

    api_url: str = Field(
        default="http://localhost:8000",
        description="Base URL of the AQP FastAPI monolith.",
    )
    control_plane_url: str = Field(
        default="http://localhost:9000",
        description="Base URL of the AQP control plane (/manage/*).",
    )
    credentials_dir: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "aqp" / "credentials",
        description="On-disk credentials store directory.",
    )
    state_dir: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "aqp" / "state",
        description="Runtime state for background processes and cached session info.",
    )
    topology_cache: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "aqp" / "topology.json",
        description="Cached topology snapshot (refreshed by `aqp-cli services list`).",
    )
    auth_state_file: str = Field(
        default="auth-session.json",
        description="Filename under credentials_dir used for cached auth tokens.",
    )
    client_state_file: str = Field(
        default="client-process.json",
        description="Filename under state_dir used for local client process metadata.",
    )
    ide_state_file: str = Field(
        default="ide-process.json",
        description="Filename under state_dir used for local Theia process metadata.",
    )
    client_log_file: str = Field(
        default="client.log",
        description="Filename under state_dir used for local client logs.",
    )
    ide_log_file: str = Field(
        default="ide.log",
        description="Filename under state_dir used for local Theia logs.",
    )
    repo_root: str = Field(
        default="",
        description=(
            "Optional monorepo root override. If empty, the CLI resolves it from this "
            "package location or CWD."
        ),
    )
    http_timeout_seconds: float = Field(default=15.0, ge=1.0)

    # --- Theia IDE entrypoint configuration ------------------------------
    theia_port: int = Field(
        default=3000,
        ge=1,
        le=65535,
        description="Local Theia IDE port (matches aqp_ide/applications/browser default).",
    )
    theia_url: str = Field(
        default="http://localhost:3000",
        description="Full URL where the local Theia IDE is served. `aqp-cli ide open` uses this.",
    )
    theia_workspace: str = Field(
        default="",
        description=(
            "Optional Theia workspace path passed positionally to `yarn start`. "
            "Empty means use whatever the Theia bundle defaults to (typically the cwd)."
        ),
    )
    theia_yarn_offline: bool = Field(
        default=False,
        description="Pass `--frozen-lockfile` to `yarn install` for reproducible CI builds.",
    )
    theia_docker_image: str = Field(
        default="aqp/aqp-ide:dev",
        description="Container image tag used by future `aqp-cli ide image` subcommands.",
    )


def get_settings() -> AqpCliSettings:
    """Return a fresh settings object. Always recomputed; never cached."""
    return AqpCliSettings()


def ensure_state_dirs(settings: AqpCliSettings) -> None:
    """Ensure all state directories exist before reading/writing state."""
    settings.credentials_dir.mkdir(parents=True, exist_ok=True)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    settings.topology_cache.parent.mkdir(parents=True, exist_ok=True)


def auth_state_path(settings: AqpCliSettings) -> Path:
    ensure_state_dirs(settings)
    return settings.credentials_dir / settings.auth_state_file


def client_state_path(settings: AqpCliSettings) -> Path:
    ensure_state_dirs(settings)
    return settings.state_dir / settings.client_state_file


def ide_state_path(settings: AqpCliSettings) -> Path:
    ensure_state_dirs(settings)
    return settings.state_dir / settings.ide_state_file


def client_log_path(settings: AqpCliSettings) -> Path:
    ensure_state_dirs(settings)
    return settings.state_dir / settings.client_log_file


def ide_log_path(settings: AqpCliSettings) -> Path:
    ensure_state_dirs(settings)
    return settings.state_dir / settings.ide_log_file


def load_auth_state(settings: AqpCliSettings) -> dict[str, Any]:
    """Load cached auth metadata from disk."""
    path = auth_state_path(settings)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def save_auth_state(settings: AqpCliSettings, payload: dict[str, Any]) -> Path:
    """Persist auth metadata to disk."""
    path = auth_state_path(settings)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def clear_auth_state(settings: AqpCliSettings) -> None:
    """Delete the cached auth metadata."""
    path = auth_state_path(settings)
    if path.exists():
        path.unlink()


def resolve_access_token(settings: AqpCliSettings) -> str:
    """Resolve a token from env overrides, the OS keyring, or the legacy JSON cache.

    Resolution order (AGENTS hard rule 53):

    1. ``AQP_CP_TOKEN`` / ``AQP_ACCESS_TOKEN`` env var (CI / break-glass).
    2. OS keyring (macOS Keychain / Windows Credential Locker / Linux
       Secret Service / ``keyrings.alt`` encrypted file).
    3. Legacy plaintext ``auth-session.json`` under
       ``settings.credentials_dir``. Kept as a one-release backward-
       compat surface so existing operators don't get logged out by
       the upgrade.

    Returns an empty string when nothing is set. NEVER raises — the
    caller decides how to react (route layer redirects to login,
    `aqp-cli` commands surface a typer.Exit with code 1).
    """
    env_token = os.environ.get("AQP_CP_TOKEN") or os.environ.get("AQP_ACCESS_TOKEN")
    if env_token:
        return env_token.strip()
    # OS keyring path
    try:
        from aqp_cli.auth.keyring_store import KeyringStore

        store = KeyringStore.for_default()
        if store.is_available():
            token = store.get_access_token()
            if isinstance(token, str) and token.strip():
                return token.strip()
    except Exception:
        # Never let keyring failures block CLI commands — fall through
        # to the legacy JSON cache. The diagnostics surface
        # (`aqp-cli auth diagnose`) is the right place to flag a
        # broken keyring.
        pass
    state = load_auth_state(settings)
    token = state.get("access_token")
    if isinstance(token, str):
        return token.strip()
    return ""


def resolve_repo_root(settings: AqpCliSettings) -> Path:
    """Best-effort repository root resolver.

    Priority:
    1) explicit `AQP_CLI_REPO_ROOT` (settings.repo_root)
    2) walk up from this file (`aqp_cli/src/aqp_cli/config.py`)
    3) current working directory
    """
    if settings.repo_root:
        return Path(settings.repo_root).expanduser().resolve()
    here = Path(__file__).resolve()
    # .../aqp_cli/src/aqp_cli/config.py -> repo root is three levels up.
    candidate = here.parents[3]
    if (candidate / "aqp_client").exists():
        return candidate
    return Path.cwd().resolve()
