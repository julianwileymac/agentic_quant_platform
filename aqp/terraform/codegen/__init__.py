"""Jinja2-driven HCL codegen for :class:`TerraformStackSpec`.

CDKTF was deprecated by HashiCorp on 2025-12-10 so the AI-driven
codegen path uses Jinja2 templates emitting native HCL. This matches
the pattern already in use elsewhere in AQP
(:mod:`aqp.streaming.templates`, :mod:`aqp.metadata.templates`).

Public surface:

- :func:`render_spec` — render a complete ``main.tf`` payload from a
  :class:`TerraformStackSpec` (the canonical entry point).
- :func:`render_module` — render just one per-cloud module template
  (useful for the frontend StackComposer preview).
- :func:`render_stack_hcl` — legacy alias for :func:`render_spec`.
- :func:`hcl_string` / :func:`hcl_value` — primitive HCL literal
  helpers (also exposed as Jinja2 filters).
- :class:`HclModuleEmitter` — back-compat OO shim.
"""
from __future__ import annotations

from aqp.terraform.codegen.base import (
    HclModuleEmitter,
    TEMPLATES_DIR,
    get_environment,
    hcl_string,
    hcl_value,
)
from aqp.terraform.codegen.wrapper import render_module, render_spec


def render_stack_hcl(spec, *, wrap: bool = True) -> str:  # type: ignore[no-untyped-def]
    """Legacy alias for :func:`render_spec`.

    The ``wrap`` keyword is accepted for backwards compat but the
    wrapper always emits the ``terraform { ... }`` block now.
    """
    return render_spec(spec)


__all__ = [
    "HclModuleEmitter",
    "TEMPLATES_DIR",
    "get_environment",
    "hcl_string",
    "hcl_value",
    "render_module",
    "render_spec",
    "render_stack_hcl",
]
