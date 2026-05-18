"""Run the 12 smoke imports requested by the verification protocol.

Each entry is run as its own python subprocess. PASS/FAIL is printed per line
with the captured stdout summary or first line of stderr on failure.
This script never modifies repo code; it only orchestrates pytest-adjacent
import checks. Exit code: 0 if all pass, 1 otherwise.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

SMOKES: list[tuple[str, str]] = [
    (
        "models_aspects",
        "from aqp.persistence.models_aspects import MetadataEntity, EntityAspect; print('OK')",
    ),
    (
        "aqp.metadata core",
        "from aqp.metadata import write_aspect, make_urn, parse_urn, to_datahub_urn, "
        "ImmutableAspectError, MetadataValidationError; print('OK')",
    ),
    (
        "aqp.metadata.openmetadata",
        "from aqp.metadata.openmetadata import MlModel, MlTestResult, EntityLineage, LineageEdge, "
        "Pipeline, PipelineTask, DatasetTable, TableColumn, TableConstraint, GlossaryTerm, "
        "Document, MlFeature, FeatureSource, MlHyperParameter, AQPOpenMetadataBase, "
        "IcebergNamespacePolicy; print('OK')",
    ),
    (
        "schema_export discover",
        "from aqp.metadata.schema_export import SchemaExporter, cli; e=SchemaExporter(); "
        "print(f'discovered {len(e.discover_models())} models')",
    ),
    (
        "datamcp tools registry",
        (
            "from aqp.data.mcp.registry import DATA_MCP_TOOLS; "
            "import aqp.data.mcp.tools; "
            "tools_of_interest=['aspect.query_entity_lineage','aspect.register_model',"
            "'aspect.get_history','data.datahub.aspect_sync','data.datahub.emit_aspect',"
            "'data.datahub.pull_aspects','iceberg.namespace_policy.get',"
            "'iceberg.namespace_policy.set']; "
            "print({t: t in DATA_MCP_TOOLS for t in tools_of_interest})"
        ),
    ),
    (
        "aqp.data.datahub surface",
        "from aqp.data.datahub import push_aspect, push_all_aspects, pull_aspect, pull_all_aspects, "
        "aqp_urn_to_datahub_entity_urn, build_datahub_aspect, ASPECT_TO_DATAHUB_CLASS, "
        "sync_aspects, sync_all; print('OK')",
    ),
    (
        "rag.document_aspects",
        "from aqp.rag.document_aspects import emit_document_aspect, emit_documents_batch, "
        "extract_glossary_terms; print('OK')",
    ),
    (
        "metadata.aspect_lookup",
        "from aqp.metadata.aspect_lookup import load_aspect, load_ml_model, load_pipeline; "
        "print('OK')",
    ),
    (
        "trading.metadata_gate",
        "from aqp.trading.metadata_gate import assert_metadata_gate, run_metadata_gate, "
        "GateOutcome; print('OK')",
    ),
    (
        "config no paper_strict knob",
        "from aqp.config import settings; "
        "assert not hasattr(settings, 'AQP_PAPER_STRICT_METADATA') and "
        "not hasattr(settings, 'paper_strict_metadata'), 'knob still present'; print('OK')",
    ),
    (
        "api routes metadata_aspects",
        "from aqp.api.routes.metadata_aspects import router; print('OK')",
    ),
    (
        "configs/paper model_urn",
        "import yaml, pathlib; "
        "cfgs=[yaml.safe_load(p.read_text()) for p in pathlib.Path('configs/paper').glob('*.yaml')]; "
        "missing=[c['session'].get('run_name') for c in cfgs if not c['session'].get('model_urn')]; "
        "assert not missing, f'configs missing model_urn: {missing}'; "
        "print(f'all {len(cfgs)} configs have model_urn')",
    ),
]


def main() -> int:
    failures: list[str] = []
    for name, snippet in SMOKES:
        proc = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True,
            text=True,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode == 0:
            summary = stdout.splitlines()[-1] if stdout else "(no stdout)"
            print(f"[PASS] {name}: {summary}")
        else:
            failures.append(name)
            # Surface the most relevant error line (last non-empty stderr line) for debugging.
            err_lines = [line for line in (stderr or "").splitlines() if line.strip()]
            err = err_lines[-1] if err_lines else "(no stderr)"
            print(f"[FAIL] {name}: exit={proc.returncode} :: {err}")
            if stderr:
                indented = textwrap.indent(stderr[-1500:], "    ")
                print(indented)
    print()
    print(f"summary: {len(SMOKES) - len(failures)}/{len(SMOKES)} passed; "
          f"failed=[{', '.join(failures) if failures else ''}]")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
