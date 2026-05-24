"""CLI configuration.

Reads in priority order:
1. CLI flags (mounted on the Typer app).
2. Environment variables prefixed ``AQP_CLI_*``.
3. ``~/.config/aqp/cli.toml`` (user config file).
4. Defaults that resolve through the topology service when reachable.
"""
from __future__ import annotations

from pathlib import Path

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
        default="http://localhost:8800",
        description="Base URL of the AQP control plane (/manage/*, /auth/*).",
    )
    credentials_dir: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "aqp" / "credentials",
        description="On-disk credentials store directory.",
    )
    topology_cache: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "aqp" / "topology.json",
        description="Cached topology snapshot (refreshed by `aqp-cli services list`).",
    )
    http_timeout_seconds: float = Field(default=15.0, ge=1.0)


def get_settings() -> AqpCliSettings:
    """Return a fresh settings object. Always recomputed; never cached."""
    return AqpCliSettings()
