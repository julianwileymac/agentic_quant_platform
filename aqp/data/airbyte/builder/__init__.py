"""Graphical Airbyte connector builder (AQP-native, phase 2).

Replaces the JSON editor in
:file:`aqp_client/src/components/airbyte/AirbyteWorkspace.tsx` with a
schema-driven form generator. The two production-ready outputs are:

- A low-code YAML manifest compatible with Airbyte's Low-Code CDK,
  emitted from :func:`state_to_yaml`.
- An AQP-native Fetcher stub
  (:class:`aqp.data.fetchers.Fetcher` subclass) emitted from
  :func:`state_to_fetcher_stub`. The stub registers via
  ``@register_source_fetcher`` and resolves all secrets through
  :class:`aqp.credentials.CredentialResolver`. This is how AQP
  satisfies the "custom Python paginator / extractor" requirement
  *without* enabling ``AIRBYTE_ENABLE_UNSAFE_CODE`` in Airbyte's
  worker container.

The builder schema lives in :mod:`aqp.data.airbyte.builder.schema`
(an opinionated subset of the Airbyte Low-Code CDK schema).
"""
from __future__ import annotations

from aqp.data.airbyte.builder.codegen_fetcher import state_to_fetcher_stub
from aqp.data.airbyte.builder.codegen_yaml import state_to_yaml
from aqp.data.airbyte.builder.inference import infer_streams
from aqp.data.airbyte.builder.schema import (
    BUILDER_SCHEMA,
    BuilderField,
    BuilderSection,
    schema_to_json,
)
from aqp.data.airbyte.builder.validate import validate_manifest

__all__ = [
    "BUILDER_SCHEMA",
    "BuilderField",
    "BuilderSection",
    "infer_streams",
    "schema_to_json",
    "state_to_fetcher_stub",
    "state_to_yaml",
    "validate_manifest",
]
