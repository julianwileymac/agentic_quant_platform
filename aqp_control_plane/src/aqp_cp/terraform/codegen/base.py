"""Jinja2 environment + HCL primitive helpers for the CP codegen layer.

Mirrors :mod:`aqp.terraform.codegen.base` 1:1 so the monolith broker
and the CP-native executor render byte-identical HCL for the same
spec content. The shared :class:`TerraformStackSpec.hcl_modules` map
is what crosses the wire — both sides MUST normalise literals the
same way or the hash-locked spec versions diverge.

Public surface:

- :data:`TEMPLATES_DIR` — :class:`pathlib.Path` to the Jinja2 root.
- :func:`get_environment` — singleton :class:`jinja2.Environment` with
  the same ``hcl`` / ``hcl_string`` / ``tfmap`` / ``tflist`` filters
  registered as the monolith.
- :func:`hcl_string` / :func:`hcl_value` — primitive HCL literal
  emitters. Also exposed as filters so templates can call
  ``{{ var | hcl }}``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

logger = logging.getLogger(__name__)


TEMPLATES_DIR: Path = Path(__file__).resolve().parent / "templates"


def hcl_string(value: str) -> str:
    """Render a Python ``str`` as an HCL double-quoted string literal."""
    return json.dumps(str(value))


def hcl_value(value: Any) -> str:
    """Render a Python value as an HCL literal.

    Type rules (must match :func:`aqp.terraform.codegen.base.hcl_value`
    so the spec hash stays stable across broker + executor):

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


__all__ = [
    "TEMPLATES_DIR",
    "get_environment",
    "hcl_string",
    "hcl_value",
]
