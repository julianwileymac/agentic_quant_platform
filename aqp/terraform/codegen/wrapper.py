"""Render a complete HCL stack from a :class:`TerraformStackSpec`.

Composes:

1. The ``terraform { required_providers = {} backend "<kind>" {} }`` header.
2. Provider configuration blocks (per cloud).
3. Variables + outputs.
4. Modules (from the canonical Jinja2 templates).
5. Free-form ``resources`` (escape hatch).
6. ``locals.common_tags`` so every resource picks up the
   AGENTS-mandated tagging convention.

The result is a single ``main.tf`` payload the runner pod writes
to disk before invoking ``terraform init / plan / apply``.

CDKTF was deprecated by HashiCorp on 2025-12-10 — the Jinja2
templates under :mod:`aqp.terraform.codegen.templates` replace it.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.terraform.codegen.base import (
    TEMPLATES_DIR,
    get_environment,
    hcl_value,
)
from aqp.terraform.spec import TerraformStackSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend rendering
# ---------------------------------------------------------------------------


def _render_backend(spec: TerraformStackSpec) -> str:
    kind = spec.backend.kind
    cfg = dict(spec.backend.config or {})
    lines = [f'  backend "{kind}" {{']
    for key, value in cfg.items():
        lines.append(f"    {key} = {hcl_value(value)}")
    lines.append("  }")
    return "\n".join(lines)


def _render_required_providers(spec: TerraformStackSpec) -> str:
    if not spec.required_providers:
        # Sensible default — local + null + random are always-needed
        # workhorses and have no auth surface.
        return (
            '  required_providers {\n'
            '    null = { source = "hashicorp/null", version = "~> 3.2" }\n'
            '    random = { source = "hashicorp/random", version = "~> 3.6" }\n'
            "  }"
        )
    parts = ["  required_providers {"]
    for name, attrs in spec.required_providers.items():
        source = attrs.get("source", f"hashicorp/{name}")
        version = attrs.get("version", "")
        version_clause = f', version = "{version}"' if version else ""
        parts.append(
            f'    {name} = {{ source = "{source}"{version_clause} }}'
        )
    parts.append("  }")
    return "\n".join(parts)


def _render_variables(spec: TerraformStackSpec) -> str:
    if not spec.variables:
        return ""
    blocks: list[str] = []
    for var in spec.variables:
        body_lines = [f'variable "{var.name}" {{']
        body_lines.append(f"  type = {var.type}")
        if var.description:
            body_lines.append(f"  description = {hcl_value(var.description)}")
        if var.default is not None:
            body_lines.append(f"  default = {hcl_value(var.default)}")
        if var.sensitive:
            body_lines.append("  sensitive = true")
        body_lines.append("}")
        blocks.append("\n".join(body_lines))
    return "\n\n".join(blocks)


def _render_outputs(spec: TerraformStackSpec) -> str:
    if not spec.outputs:
        return ""
    blocks: list[str] = []
    for out in spec.outputs:
        body_lines = [f'output "{out.name}" {{']
        body_lines.append(f"  value = {out.value}")
        if out.description:
            body_lines.append(f"  description = {hcl_value(out.description)}")
        if out.sensitive:
            body_lines.append("  sensitive = true")
        body_lines.append("}")
        blocks.append("\n".join(body_lines))
    return "\n\n".join(blocks)


def _render_modules(spec: TerraformStackSpec) -> str:
    if not spec.modules:
        return ""
    blocks: list[str] = []
    for m in spec.modules:
        body_lines = [f'module "{m.name}" {{']
        body_lines.append(f"  source = {hcl_value(m.source)}")
        if m.version:
            body_lines.append(f"  version = {hcl_value(m.version)}")
        for key, value in (m.variables or {}).items():
            body_lines.append(f"  {key} = {hcl_value(value)}")
        if m.providers:
            body_lines.append("  providers = {")
            for alias, target in m.providers.items():
                body_lines.append(f"    {alias} = {target}")
            body_lines.append("  }")
        body_lines.append("}")
        blocks.append("\n".join(body_lines))
    return "\n\n".join(blocks)


def _render_resources(spec: TerraformStackSpec) -> str:
    if not spec.resources:
        return ""
    blocks: list[str] = []
    for r in spec.resources:
        body_lines = [f'resource "{r.type}" "{r.name}" {{']
        for key, value in (r.body or {}).items():
            body_lines.append(f"  {key} = {hcl_value(value)}")
        body_lines.append("}")
        blocks.append("\n".join(body_lines))
    return "\n\n".join(blocks)


def _render_locals(spec: TerraformStackSpec) -> str:
    tags = dict(spec.common_tags or {})
    tags.setdefault("environment", spec.environment)
    tags.setdefault("managed-by", "terraform")
    tags.setdefault("component", spec.module_kind)
    if spec.organization_id:
        tags.setdefault("organization", spec.organization_id)
    if spec.workspace_id:
        tags.setdefault("workspace", spec.workspace_id)
    body_lines = ["locals {", "  common_tags = {"]
    for key, value in tags.items():
        body_lines.append(f"    {key} = {hcl_value(value)}")
    body_lines.append("  }")
    body_lines.append("}")
    return "\n".join(body_lines)


def _render_module_template(spec: TerraformStackSpec) -> str:
    """When ``module_kind`` matches a known per-cloud template, render it.

    Falls back to an empty string when no matching template exists
    (composite stacks rely on ``modules:`` + ``resources:`` only).
    """
    env = get_environment()
    candidates = [
        f"{spec.module_kind}_{spec.cloud_provider}.tf.j2",
        f"{spec.module_kind}.tf.j2",
    ]
    for name in candidates:
        if (TEMPLATES_DIR / name).exists():
            template = env.get_template(name)
            return template.render(spec=spec)
    return ""


# ---------------------------------------------------------------------------
# Public render entry points
# ---------------------------------------------------------------------------


def render_spec(spec: TerraformStackSpec) -> str:
    """Render the complete HCL payload for a stack.

    The output is a single string the runner pod writes to
    ``<workspace>/main.tf`` before invoking ``terraform init``.
    """
    parts: list[str] = []
    parts.append(
        "# Generated by aqp/terraform/codegen — DO NOT EDIT BY HAND.\n"
        "# Source spec hash: " + spec.snapshot_hash()
    )
    # terraform { ... } header
    parts.append(
        "terraform {\n"
        + _render_required_providers(spec)
        + "\n"
        + _render_backend(spec)
        + "\n}"
    )
    locals_block = _render_locals(spec)
    parts.append(locals_block)

    variables = _render_variables(spec)
    if variables:
        parts.append(variables)

    module_body = _render_module_template(spec)
    if module_body:
        parts.append(module_body)

    modules = _render_modules(spec)
    if modules:
        parts.append(modules)

    resources = _render_resources(spec)
    if resources:
        parts.append(resources)

    outputs = _render_outputs(spec)
    if outputs:
        parts.append(outputs)

    return "\n\n".join(parts) + "\n"


def render_module(
    *,
    module_kind: str,
    cloud_provider: str,
    variables: dict[str, Any] | None = None,
) -> str:
    """Render just the body of one module template (preview / composer)."""
    env = get_environment()
    candidates = [
        f"{module_kind}_{cloud_provider}.tf.j2",
        f"{module_kind}.tf.j2",
    ]
    for name in candidates:
        if (TEMPLATES_DIR / name).exists():
            template = env.get_template(name)
            return template.render(variables=(variables or {}))
    return f"# No template found for module_kind={module_kind} cloud={cloud_provider}\n"


__all__ = ["render_module", "render_spec"]
