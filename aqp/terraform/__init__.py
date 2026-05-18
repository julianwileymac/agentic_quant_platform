"""Terraform IaC control plane — 5th sibling spec-runtime.

Mirrors the layout of :mod:`aqp.bots` / :mod:`aqp.rl` /
:mod:`aqp.analysis` / :mod:`aqp.agents` — a hash-locked
:class:`TerraformStackSpec` driven by a single
:class:`TerraformRuntime` that:

1. Snapshots the spec into ``terraform_stack_spec_versions`` (rule 43).
2. Opens a :class:`TerraformRun` ledger row (rule 42 + rule 34).
3. Drives ``terraform plan / apply / destroy`` through the
   :class:`TerraformExecutor` (local subprocess or HCP HTTP API).
4. Captures stdout / stderr + the structured ``tfplan.json`` artifact
   into S3 / MinIO.
5. Streams progress via :mod:`aqp.tasks._progress` so existing
   ``/chat/stream/<task_id>`` consumers light up unchanged.

HCL is generated via :mod:`aqp.terraform.codegen` Jinja2 templates
(CDKTF was deprecated by HashiCorp on 2025-12-10).
"""
from __future__ import annotations

from aqp.terraform.runtime import TerraformRuntime, TerraformRunResult
from aqp.terraform.spec import (
    TerraformStackSpec,
    TerraformStateBackend,
    load_specs_from_dir,
)

__all__ = [
    "TerraformRunResult",
    "TerraformRuntime",
    "TerraformStackSpec",
    "TerraformStateBackend",
    "load_specs_from_dir",
]
