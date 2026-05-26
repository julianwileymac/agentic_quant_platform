"""Jinja2-driven HCL codegen for the CP-side TerraformRuntime (rule 42).

CDKTF was deprecated by HashiCorp on 2025-12-10. The CP-side codegen
mirrors the in-monolith :mod:`aqp.terraform.codegen` tree so the
monolith broker and the CP-native executor render identical HCL for
the same logical stack.

Public surface:

- :func:`render_module` — render one Jinja2 template by module kind
  and cloud provider. Returns the HCL body as a string.
- :func:`render_bundle` — render a complete ``hcl_modules`` map ready
  to drop into a :class:`aqp_platform_core.models.terraform.TerraformStackSpec`.
- :func:`hcl_string` / :func:`hcl_value` — primitive HCL literal
  helpers (also exposed as Jinja2 filters).

The templates directory ships eleven files:

- ``generic.tf.j2``
- ``agents_local.tf.j2``
- ``cloudflare_edge.tf.j2``
- ``faas_local.tf.j2``
- ``secrets_local.tf.j2``
- ``storage_aws.tf.j2`` / ``_azure.tf.j2`` / ``_gcp.tf.j2`` / ``_local.tf.j2``
- ``bedrock_agentcore.tf.j2`` — Phase C (Bedrock AgentCore Runtime + Memory + Gateway)
- ``bedrock_kb_oss.tf.j2`` — Phase C (Bedrock Knowledge Base + OpenSearch Serverless)
"""
from __future__ import annotations

from aqp_cp.terraform.codegen.base import (
    TEMPLATES_DIR,
    get_environment,
    hcl_string,
    hcl_value,
)
from aqp_cp.terraform.codegen.wrapper import render_bundle, render_module

__all__ = [
    "TEMPLATES_DIR",
    "get_environment",
    "hcl_string",
    "hcl_value",
    "render_bundle",
    "render_module",
]
