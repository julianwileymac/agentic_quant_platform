"""Jinja2 environment + HCL primitive helpers for the codegen layer.

This module is the bottom of the codegen stack — it owns the
``TEMPLATES_DIR`` constant, the lazy Jinja2 :class:`Environment`
factory, and the HCL literal helpers (``hcl_string`` / ``hcl_value``).
The richer :mod:`aqp.terraform.codegen.wrapper` composes everything
into a full ``main.tf`` payload.

Public surface:

- :data:`TEMPLATES_DIR` — :class:`pathlib.Path` to the Jinja2 root.
- :func:`get_environment` — singleton :class:`jinja2.Environment` with
  AQP's ``hcl`` / ``hcl_string`` / ``tfmap`` / ``tflist`` filters.
- :func:`hcl_string` / :func:`hcl_value` — primitive HCL literal
  emitters. Also exposed as filters so templates can call
  ``{{ var | hcl }}``.
- :class:`HclModuleEmitter` — back-compat shim delegating to
  :func:`aqp.terraform.codegen.wrapper.render_spec`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

logger = logging.getLogger(__name__)


TEMPLATES_DIR: Path = Path(__file__).resolve().parent / "templates"


# ---------------------------------------------------------------------------
# HCL primitive helpers
# ---------------------------------------------------------------------------


def hcl_string(value: str) -> str:
    """Render a Python ``str`` as an HCL double-quoted string literal."""
    return json.dumps(str(value))


def hcl_value(value: Any) -> str:
    """Render a Python value as an HCL literal.

    Type rules:

    - ``None`` -> ``null``
    - ``bool`` -> ``true`` / ``false``
    - ``int`` / ``float`` -> numeric literal
    - ``str`` -> double-quoted with JSON-style escaping
    - ``dict`` -> HCL map (``{ k = v, ... }``)
    - ``list`` / ``tuple`` / ``set`` -> HCL list (``["v", ...]``)
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return hcl_string(value)
    if isinstance(value, dict):
        return _hcl_map(value)
    if isinstance(value, (list, tuple, set)):
        return _hcl_list(value)
    return json.dumps(value)


def _hcl_map(value: dict[str, Any]) -> str:
    if not value:
        return "{}"
    parts = [f"{_clean_key(k)} = {hcl_value(v)}" for k, v in value.items()]
    return "{ " + ", ".join(parts) + " }"


def _hcl_list(value: Any) -> str:
    items = list(value)
    if not items:
        return "[]"
    return "[" + ", ".join(hcl_value(v) for v in items) + "]"


def _clean_key(key: str) -> str:
    s = str(key)
    if s and (s[0].isalpha() or s[0] == "_") and all(c.isalnum() or c == "_" for c in s):
        return s
    return json.dumps(s)


# ---------------------------------------------------------------------------
# Jinja2 environment
# ---------------------------------------------------------------------------


_ENV: Environment | None = None


def get_environment() -> Environment:
    """Return the process-wide :class:`jinja2.Environment`.

    The environment uses ``StrictUndefined`` so templates that
    reference unknown variables raise loudly at render time rather
    than silently emitting blanks.
    """
    global _ENV
    if _ENV is None:
        _ENV = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            autoescape=False,
        )
        _ENV.filters["hcl"] = hcl_value
        _ENV.filters["hcl_string"] = hcl_string
        _ENV.filters["tfmap"] = _hcl_map
        _ENV.filters["tflist"] = _hcl_list
    return _ENV


# ---------------------------------------------------------------------------
# Back-compat shim
# ---------------------------------------------------------------------------


class HclModuleEmitter:
    """Render a :class:`TerraformStackSpec` to HCL via Jinja2.

    Kept for callers that haven't migrated to the cleaner
    :func:`aqp.terraform.codegen.wrapper.render_spec` entry point.
    """

    def emit(self, spec: Any) -> str:
        from aqp.terraform.codegen.wrapper import render_spec

        return render_spec(spec)


__all__ = [
    "HclModuleEmitter",
    "TEMPLATES_DIR",
    "get_environment",
    "hcl_string",
    "hcl_value",
]
