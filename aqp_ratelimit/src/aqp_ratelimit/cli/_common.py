"""Helpers shared by the CLI subcommands."""
from __future__ import annotations

import os


def resolve_user_id_from_env() -> str:
    """Return the calling user id.

    Order:

    1. ``AQP_USER_ID`` env (for CI / scripts).
    2. ``aqp config`` token resolution via the monolith helper.
    3. Fall back to ``"local-dev"`` so offline kernels don't break.
    """
    user_id = os.environ.get("AQP_USER_ID")
    if user_id:
        return str(user_id)
    try:
        from aqp.cli.config_cmd import resolve_calling_user_id

        return str(resolve_calling_user_id())
    except Exception:  # noqa: BLE001
        return "local-dev"


__all__ = ["resolve_user_id_from_env"]
