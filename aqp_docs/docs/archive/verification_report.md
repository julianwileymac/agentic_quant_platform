---
title: 'AQP Metadata & Lineage Consolidation Verification Report'
summary: 'Execution environment blocker prevented command execution before Python startup: `Sandbox policy workspace_readwrite is not supported on this system. Ensure the sandbox helper binary is available, o...'
owner: docs-team
last_reviewed: 2026-05-25
audience: both
---

> Archived context note: point-in-time verification output retained for
> traceability. Current operational checks live in active runbooks under
> `aqp_docs/operations/*`. See `aqp_docs/archive/README.md`.

# AQP Metadata & Lineage Consolidation Verification Report

## Smoke imports

Execution environment blocker prevented command execution before Python startup:
`Sandbox policy 'workspace_readwrite' is not supported on this system. Ensure the sandbox helper binary is available, or use 'insecure_none'. Reason: Windows sandbox helper only provides network proxy, not filesystem isolation`.

- `python -c "from aqp.persistence.models_aspects import MetadataEntity, EntityAspect; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.metadata import write_aspect, make_urn, parse_urn, to_datahub_urn, ImmutableAspectError, MetadataValidationError; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.metadata.openmetadata import MlModel, MlTestResult, EntityLineage, LineageEdge, Pipeline, PipelineTask, DatasetTable, TableColumn, TableConstraint, GlossaryTerm, Document, MlFeature, FeatureSource, MlHyperParameter, AQPOpenMetadataBase, IcebergNamespacePolicy; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.metadata.schema_export import SchemaExporter, cli; e=SchemaExporter(); print(f'discovered {len(e.discover_models())} models')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.data.mcp.registry import DATA_MCP_TOOLS; import aqp.data.mcp.tools; tools_of_interest=['aspect.query_entity_lineage','aspect.register_model','aspect.get_history','data.datahub.aspect_sync','data.datahub.emit_aspect','data.datahub.pull_aspects','iceberg.namespace_policy.get','iceberg.namespace_policy.set']; print({t: t in DATA_MCP_TOOLS for t in tools_of_interest})"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.data.datahub import push_aspect, push_all_aspects, pull_aspect, pull_all_aspects, aqp_urn_to_datahub_entity_urn, build_datahub_aspect, ASPECT_TO_DATAHUB_CLASS, sync_aspects, sync_all; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.rag.document_aspects import emit_document_aspect, emit_documents_batch, extract_glossary_terms; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.metadata.aspect_lookup import load_aspect, load_ml_model, load_pipeline; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.trading.metadata_gate import assert_metadata_gate, run_metadata_gate, GateOutcome; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.config import settings; assert not hasattr(settings, 'AQP_PAPER_STRICT_METADATA') and not hasattr(settings, 'paper_strict_metadata'), 'knob still present'; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "from aqp.api.routes.metadata_aspects import router; print('OK')"` - **FAIL** (infrastructure blocker; command did not execute)
- `python -c "import yaml, pathlib; cfgs=[yaml.safe_load(p.read_text()) for p in pathlib.Path('configs/paper').glob('*.yaml')]; missing=[c['session'].get('run_name') for c in cfgs if not c['session'].get('model_urn')]; assert not missing, f'configs missing model_urn: {missing}'; print(f'all {len(cfgs)} configs have model_urn')"` - **FAIL** (infrastructure blocker; command did not execute)

## Pytest suites

No pytest suites executed; shell command startup was blocked by the same infrastructure error.

| suite | passed | failed | duration |
| --- | ---: | ---: | ---: |
| `tests/persistence/test_aspect_immutability.py tests/persistence/test_write_aspect_versioning.py tests/persistence/test_aspect_backfill.py` | N/A | N/A | N/A |
| `tests/metadata/openmetadata/` | N/A | N/A | N/A |
| `tests/data/mcp/test_aspect_tools.py` | N/A | N/A | N/A |
| `tests/metadata/test_schema_export.py` | N/A | N/A | N/A |
| `tests/rag/test_document_aspects.py` | N/A | N/A | N/A |
| `tests/tasks/test_ml_test_aspect_integration.py` | N/A | N/A | N/A |
| `tests/trading/test_metadata_gate.py tests/trading/test_paper_config_yaml.py` | N/A | N/A | N/A |
| `tests/api/test_metadata_aspects_routes.py` | N/A | N/A | N/A |
| `tests/data/datahub/test_aspect_mapping.py tests/data/datahub/test_aspect_emitter.py tests/data/datahub/test_aspect_puller.py tests/data/mcp/test_aspect_sync_tool.py` | N/A | N/A | N/A |
| `tests/data/catalog/test_namespace_policy.py tests/metadata/openmetadata/test_iceberg_namespace.py tests/data/mcp/test_namespace_policy_tools.py` | N/A | N/A | N/A |

Consolidated pytest summary: **0 passed, 0 failed, 0 executed** (infrastructure-blocked run).

## Schema exporter end-to-end

- Command (`python -m aqp.metadata.schema_export --format all --output-root <temp-dir>`): **FAIL** (infrastructure blocker; command did not execute)
- `json` file count: **N/A**
- `avro` file count: **N/A**
- `pdl` file count: **N/A**

## DataMCP tool count

- Command (`python -c "from aqp.data.mcp.registry import DATA_MCP_TOOLS; import aqp.data.mcp.tools; print(f'tool_count={len(DATA_MCP_TOOLS)}')"`): **FAIL** (infrastructure blocker; command did not execute)
- Final number: **N/A**

## Frontend typecheck

- `cd aqp_client && pnpm exec tsc --noEmit -p .`: **FAIL** (infrastructure blocker; command did not execute)
- Dependency fallback (`npm install --silent`) was not reachable because command execution itself failed before process start.

## Aggregate verdict

**RED**

Failures:
- Shell command execution is blocked in this environment by unsupported sandbox policy (`workspace_readwrite`), preventing all smoke imports, pytest runs, schema export smoke test, DataMCP count command, and frontend typecheck.
