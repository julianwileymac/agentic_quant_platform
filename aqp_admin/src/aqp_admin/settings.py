"""Settings for the aqp_admin backend.

Reads ``AQP_ADMIN_*`` environment variables and falls back to safe local
defaults. Per AQP rule 7 the project never instantiates a fresh settings
object directly; consumers go through :func:`get_settings`.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AQP_ADMIN_", env_file=None, extra="ignore")

    api_url: str = Field(default="http://localhost:8000", description="AQP monolith base URL.")
    control_plane_url: str = Field(
        default="http://localhost:8800", description="aqp_control_plane base URL."
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3003"],
        description="Allowed CORS origins for the admin SPA.",
    )
    audit_sink: str = Field(
        default="jsonl",
        description="Audit sink: 'jsonl' for local file or 'postgres' for shared ledger.",
    )
    audit_jsonl_path: str = Field(
        default="./admin_audit.jsonl",
        description="JSONL fallback path when audit_sink == 'jsonl'.",
    )


@lru_cache(maxsize=1)
def get_settings() -> AdminSettings:
    return AdminSettings()
