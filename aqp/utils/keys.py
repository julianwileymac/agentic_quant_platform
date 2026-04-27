"""Lightweight env-var helpers ported from FinRobot's ``register_keys_from_json``.

When you have a JSON file with API credentials laid out as::

    {
      "FINNHUB_API_KEY": "abc",
      "FMP_API_KEY": "def",
      "OPENAI_API_KEY": "ghi"
    }

calling :func:`register_keys_from_json` injects every key into the
process environment so libraries that read keys from ``os.environ`` work
without code changes. Useful when sharing credential bundles between
``agentic_assistants`` and ``agentic_quant_platform`` development.

Lifted from `FinRobot <https://github.com/AI4Finance-Foundation/FinRobot>`_'s
``finrobot/utils.py``; reduced to just the env-injection bit (the
original had Autogen-specific glue we don't need).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def register_keys_from_json(path: str | Path, *, override: bool = False) -> list[str]:
    """Load ``path`` (JSON dict) and ``os.environ.update`` from it.

    Parameters
    ----------
    path:
        Filesystem path to a JSON file with string keys + string values.
    override:
        When ``False`` (default), keys already present in ``os.environ``
        are preserved. When ``True`` they are overwritten by the file.

    Returns
    -------
    list[str]
        The names of the env variables that were set or updated.
    """
    target = Path(path).expanduser()
    if not target.exists():
        logger.warning("register_keys_from_json: %s not found", target)
        return []

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_keys_from_json: could not parse %s: %s", target, exc)
        return []

    if not isinstance(payload, dict):
        logger.warning("register_keys_from_json: %s is not a JSON object", target)
        return []

    written: list[str] = []
    for key, value in payload.items():
        if not isinstance(key, str) or not isinstance(value, (str, int, float)):
            continue
        env_key = key.upper()
        if not override and os.environ.get(env_key):
            continue
        os.environ[env_key] = str(value)
        written.append(env_key)
    return written


__all__ = ["register_keys_from_json"]
