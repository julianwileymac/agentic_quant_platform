"""Configuration package — global Settings + layered overlay resolution.

Public surface:

- :data:`settings`: the lru-cached process-wide :class:`Settings` instance.
  Continues to support ``from aqp.config import settings`` for backwards
  compatibility with everything that was written against the old single-file
  ``aqp/config.py``.
- :func:`get_settings`: factory used by tests / fixtures that need to reset
  the cache.
- :class:`Settings`: the Pydantic settings model itself.
- :func:`resolve_config`, :func:`set_overlay`, :func:`clear_overlay`,
  :func:`get_overlay`: the layered config API (global > org > team > user >
  workspace > project) backed by the :class:`ConfigOverlayRow` table.
- :mod:`aqp.config.defaults`: the deterministic ``default-*`` UUID constants
  used by :ref:`migration 0017 <alembic-0017>` and the auth package.
"""
from __future__ import annotations

from aqp.config.defaults import (
    DEFAULT_LAB_ID,
    DEFAULT_LAB_NAME,
    DEFAULT_LAB_SLUG,
    DEFAULT_ORG_ID,
    DEFAULT_ORG_NAME,
    DEFAULT_ORG_SLUG,
    DEFAULT_PROJECT_ID,
    DEFAULT_PROJECT_NAME,
    DEFAULT_PROJECT_SLUG,
    DEFAULT_TEAM_ID,
    DEFAULT_TEAM_NAME,
    DEFAULT_TEAM_SLUG,
    DEFAULT_USER_DISPLAY_NAME,
    DEFAULT_USER_EMAIL,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
    DEFAULT_WORKSPACE_NAME,
    DEFAULT_WORKSPACE_SLUG,
)
from aqp.config.layered import (
    AtomicDict,
    UNSET,
    atomic_dict,
    clear_overlay,
    flat_merge_dicts,
    get_overlay,
    get_path,
    merge_dicts,
    resolve_config,
    set_overlay,
)
from aqp.config.settings import Settings, get_settings, settings

__all__ = [
    "AtomicDict",
    "DEFAULT_LAB_ID",
    "DEFAULT_LAB_NAME",
    "DEFAULT_LAB_SLUG",
    "DEFAULT_ORG_ID",
    "DEFAULT_ORG_NAME",
    "DEFAULT_ORG_SLUG",
    "DEFAULT_PROJECT_ID",
    "DEFAULT_PROJECT_NAME",
    "DEFAULT_PROJECT_SLUG",
    "DEFAULT_TEAM_ID",
    "DEFAULT_TEAM_NAME",
    "DEFAULT_TEAM_SLUG",
    "DEFAULT_USER_DISPLAY_NAME",
    "DEFAULT_USER_EMAIL",
    "DEFAULT_USER_ID",
    "DEFAULT_WORKSPACE_ID",
    "DEFAULT_WORKSPACE_NAME",
    "DEFAULT_WORKSPACE_SLUG",
    "Settings",
    "UNSET",
    "atomic_dict",
    "clear_overlay",
    "flat_merge_dicts",
    "get_overlay",
    "get_path",
    "get_settings",
    "merge_dicts",
    "resolve_config",
    "set_overlay",
    "settings",
]
