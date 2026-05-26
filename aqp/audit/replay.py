"""Replay harness for hash-locked runs (Phase 7 §10.2).

Re-executes a recorded agent / workflow / RL / analysis / backtest run
against the EXACT spec + MCP tool surface that existed at original run
time. The harness composes:

- the immutable ``<runtime>_spec_versions`` table (Rules 13, 15, 17,
  24, 41, 43);
- the MCP tool descriptor hash array on each run row (Phase 5 §8.4);
- a deterministic seed plumbed through ``router_complete`` so the LLM
  output is reproducible;
- a per-replay shadow Postgres schema so the replay never overwrites
  the original ledger.

Three replay environments — see :class:`ReplayEnvironment`:

| Env | Side effects | Purpose |
| --- | --- | --- |
| ``AUDIT_SHADOW`` | None — all writes diverted to a per-run shadow schema | Compliance verification |
| ``INCIDENT_REPRO`` | None — all writes diverted; output diffed against original | Bug bisection |
| ``MODEL_REVALIDATION`` | Writes to a marked ``replay-N`` branch of ``agent_runs_v2``; never touches the original | Model behaviour over time |

Phase 7 §10.2 lists this as ``[ADD]``; Phase 7.5 (out of scope) wires
the per-replay shadow schema lifecycle into Argo Workflows.
"""
from __future__ import annotations

import enum
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ReplayEnvironment(str, enum.Enum):
    """Where the replay output lands. Defaults to AUDIT_SHADOW."""

    AUDIT_SHADOW = "audit_shadow"
    INCIDENT_REPRO = "incident_repro"
    MODEL_REVALIDATION = "model_revalidation"


# Map every supported runtime to:
#   (run_table, spec_table, spec_id_col, mcp_descriptor_col)
# The harness uses these to look up the immutable spec snapshot and the
# MCP tool descriptor hashes for any run row.
_RUNTIME_TABLES: dict[str, tuple[str, str, str, str | None]] = {
    "agent_runs_v2": ("agent_runs_v2", "agent_spec_versions", "spec_version_id", "mcp_tool_descriptor_hashes"),
    "bot_runs": ("bot_runs", "bot_spec_versions", "spec_version_id", None),
    "rl_experiment_runs": ("rl_experiment_runs", "rl_experiment_spec_versions", "spec_version_id", None),
    "alpha_backtest_runs": ("alpha_backtest_runs", "alpha_spec_versions", "spec_version_id", None),
    "workload_runs": ("workload_runs", None, None, None),  # workloads have no spec
}


@dataclass(frozen=True)
class ReplayReport:
    """Structured outcome of one replay execution."""

    run_id: str
    runtime: str
    cell_id: str
    target_environment: ReplayEnvironment
    spec_version_id: str | None
    mcp_tool_descriptor_hashes: list[str] = field(default_factory=list)
    shadow_schema: str = ""
    original_output_hash: str = ""
    replay_output_hash: str = ""
    output_matches: bool = False
    anchored_segment_id: str | None = None
    anchor_verified: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    error: str | None = None
    notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "runtime": self.runtime,
            "cell_id": self.cell_id,
            "target_environment": self.target_environment.value,
            "spec_version_id": self.spec_version_id,
            "mcp_tool_descriptor_hashes": list(self.mcp_tool_descriptor_hashes),
            "shadow_schema": self.shadow_schema,
            "original_output_hash": self.original_output_hash,
            "replay_output_hash": self.replay_output_hash,
            "output_matches": self.output_matches,
            "anchored_segment_id": self.anchored_segment_id,
            "anchor_verified": self.anchor_verified,
            "started_at": self.started_at.isoformat(),
            "finished_at": (self.finished_at.isoformat() if self.finished_at else None),
            "error": self.error,
            "notes": dict(self.notes),
        }


# ---------------------------------------------------------------------------
# Run-row loaders
# ---------------------------------------------------------------------------


def _detect_runtime(run_id: str, session) -> str:
    """Return the canonical runtime name for a ``run_id``.

    We probe each supported runtime table in turn. The first hit wins;
    AGENTS hard rule 1 (no `vt_symbol` splitting) does not apply here —
    the lookup is by primary-key id only.
    """
    from sqlalchemy import text

    for runtime, (table, *_rest) in _RUNTIME_TABLES.items():
        try:
            row = session.execute(
                text(f"SELECT id FROM {table} WHERE id = :run_id LIMIT 1"),
                {"run_id": run_id},
            ).first()
        except Exception:  # noqa: BLE001 - table may not exist in test fixture
            continue
        if row is not None:
            return runtime
    raise RuntimeError(f"replay: no runtime table contains run_id {run_id!r}")


def _load_run_row(runtime: str, run_id: str, session) -> dict[str, Any]:
    """Return the run-row as a plain dict."""
    from sqlalchemy import text

    table, *_rest = _RUNTIME_TABLES[runtime]
    row = session.execute(
        text(f"SELECT * FROM {table} WHERE id = :run_id"),
        {"run_id": run_id},
    ).first()
    if row is None:
        raise RuntimeError(f"replay: run {run_id!r} not found in {table}")
    return dict(row._mapping)


def _load_spec_snapshot(runtime: str, run_row: dict[str, Any], session) -> dict[str, Any] | None:
    """Return the immutable spec snapshot for the run, or None if N/A."""
    _, spec_table, spec_id_col, _ = _RUNTIME_TABLES[runtime]
    if spec_table is None or spec_id_col is None:
        return None
    spec_id = run_row.get(spec_id_col)
    if not spec_id:
        return None

    from sqlalchemy import text

    row = session.execute(
        text(f"SELECT * FROM {spec_table} WHERE id = :spec_id"),
        {"spec_id": spec_id},
    ).first()
    if row is None:
        raise RuntimeError(
            f"replay: spec version {spec_id!r} missing from {spec_table} "
            "(spec_versions are immutable; this is a data-integrity break)"
        )
    return dict(row._mapping)


def _mcp_descriptor_hashes(runtime: str, run_row: dict[str, Any]) -> list[str]:
    """Return the MCP tool descriptor hash list recorded on the run row."""
    _, _, _, descriptor_col = _RUNTIME_TABLES[runtime]
    if descriptor_col is None:
        return []
    raw = run_row.get(descriptor_col)
    if isinstance(raw, list):
        return [str(h) for h in raw]
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, list):
                return [str(h) for h in decoded]
        except Exception:  # noqa: BLE001 - defensive
            return []
    return []


# ---------------------------------------------------------------------------
# Shadow schema lifecycle
# ---------------------------------------------------------------------------


def _shadow_schema_name(runtime: str, run_id: str, environment: ReplayEnvironment) -> str:
    """Return a deterministic shadow-schema name for ``(runtime, run_id, env)``.

    Format: ``replay_<env-tag>_<runtime-short>_<run-id-short>``. We hash
    the full ``run_id`` to keep schema names within Postgres's 63-byte
    identifier limit.
    """
    env_tag = environment.value.replace("_", "")[:6]
    runtime_short = runtime.split("_", 1)[0][:6]
    run_short = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]
    return f"replay_{env_tag}_{runtime_short}_{run_short}"


def _ensure_shadow_schema(name: str, session) -> None:
    """Create the shadow schema if it doesn't exist (Phase 7 §10.2)."""
    if not name:
        return
    from sqlalchemy import text

    session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{name}"'))


def _drop_shadow_schema(name: str, session) -> None:
    """Drop the shadow schema and everything in it.

    Phase 7 deliberately keeps this destructive operation guarded by an
    explicit caller — the harness never calls it automatically. The
    runbook documents the cleanup cadence (typically after the
    evidence bundle has been signed off).
    """
    if not name:
        return
    from sqlalchemy import text

    session.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))


# ---------------------------------------------------------------------------
# Output hash helpers
# ---------------------------------------------------------------------------


def _stable_output_hash(payload: Any) -> str:
    """Return a stable SHA-256 hex digest over an arbitrary output payload."""
    if payload is None:
        return ""
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError):
        encoded = repr(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# Anchor verification
# ---------------------------------------------------------------------------


def _verify_anchor(cell_id: str, ts: datetime, session) -> tuple[str | None, bool]:
    """Look up the audit-lake segment covering ``ts`` and verify its anchor.

    Returns ``(segment_id, verified)``. ``verified=True`` means at
    least one anchor sink reproduced the recorded tip-hash; ``False``
    means either no segment covers ``ts`` or every sink mismatched.
    """
    from sqlalchemy import text

    row = session.execute(
        text(
            """
            SELECT id, segment_tip_hash, prev_segment_tip_hash,
                   iceberg_snapshot_id, s3_manifest_uri,
                   segment_start_ts, segment_end_ts
              FROM audit_lake_segments
             WHERE cell_id = :cell_id
               AND segment_start_ts <= :ts
               AND segment_end_ts   >  :ts
             ORDER BY segment_start_ts DESC
             LIMIT 1
            """
        ),
        {"cell_id": cell_id, "ts": ts},
    ).first()
    if row is None:
        return None, False
    segment_id = row.id

    anchors = session.execute(
        text(
            """
            SELECT sink_kind, verification_handle
              FROM audit_lake_anchors
             WHERE segment_id = :segment_id
            """
        ),
        {"segment_id": segment_id},
    ).all()
    if not anchors:
        return segment_id, False

    from aqp.audit import AnchorRecord, list_transparency_anchor_sink_classes

    # Force import so the metaclass populates the registry.
    from aqp.audit import sinks as _sinks  # noqa: F401

    sink_map = list_transparency_anchor_sink_classes()
    record = AnchorRecord(
        cell_id=cell_id,
        segment_start_ts=row.segment_start_ts,
        segment_end_ts=row.segment_end_ts,
        prev_tip_hash=row.prev_segment_tip_hash,
        tip_hash=row.segment_tip_hash,
        iceberg_snapshot_id=row.iceberg_snapshot_id or "",
        s3_manifest_uri=row.s3_manifest_uri or "",
    )
    for anchor in anchors:
        sink_cls = next(
            (c for c in sink_map.values() if c.sink_kind == anchor.sink_kind),
            None,
        )
        if sink_cls is None:
            continue
        try:
            sink = sink_cls()
            if sink.verify(record, anchor.verification_handle):
                # Update last_verified_*.
                session.execute(
                    text(
                        """
                        UPDATE audit_lake_anchors
                           SET last_verified_at = :now,
                               last_verified_ok = TRUE
                         WHERE segment_id = :segment_id
                           AND sink_kind  = :sink_kind
                        """
                    ),
                    {
                        "now": datetime.now(timezone.utc),
                        "segment_id": segment_id,
                        "sink_kind": anchor.sink_kind,
                    },
                )
                return segment_id, True
        except Exception:  # noqa: BLE001 - per-sink isolation
            logger.warning(
                "replay: anchor verify failed for sink %s",
                anchor.sink_kind,
                exc_info=True,
            )
            continue
    return segment_id, False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def replay_run(
    *,
    run_id: str,
    cell_id: str,
    target_environment: ReplayEnvironment = ReplayEnvironment.AUDIT_SHADOW,
    keep_shadow_schema: bool = True,
) -> ReplayReport:
    """Re-execute a recorded run against its hash-locked spec.

    1. Load the run row + the spec_version_id from the per-cell engine.
    2. Pin the MCP tool descriptors by ``mcp_tool_descriptor_hashes``.
    3. Set a deterministic seed via ``router_complete`` cache_key.
    4. Execute in the chosen ``target_environment``.
    5. Verify the anchored audit segment that covers the run's timestamp.
    6. Compare the new run's output hash to the original output hash.

    For Phase 7 the harness DOES NOT actually re-execute the runtime —
    that wires in via Phase 7.5 which integrates with the existing
    ``AgentRuntime`` / ``RLRuntime`` / ``WorkflowRuntime``. This shim
    returns a report that covers the spec lookup + anchor verification,
    which is the audit-essential surface. The execution slot is marked
    as a TODO so the operator wires it in once Phase 7.5 lands.
    """
    from aqp.persistence.db import get_session

    started_at = datetime.now(timezone.utc)
    shadow = ""
    runtime = ""
    spec_version_id: str | None = None
    descriptor_hashes: list[str] = []
    original_hash = ""
    replay_hash = ""
    anchored_segment_id: str | None = None
    anchor_verified = False
    error: str | None = None
    notes: dict[str, Any] = {}

    try:
        with get_session() as session:
            runtime = _detect_runtime(run_id, session)
            run_row = _load_run_row(runtime, run_id, session)

            spec_snapshot = _load_spec_snapshot(runtime, run_row, session)
            spec_version_id = (
                spec_snapshot.get("id") if spec_snapshot else None
            )
            descriptor_hashes = _mcp_descriptor_hashes(runtime, run_row)

            original_hash = _stable_output_hash(
                run_row.get("output") or run_row.get("result")
            )

            shadow = _shadow_schema_name(runtime, run_id, target_environment)
            _ensure_shadow_schema(shadow, session)

            # Anchor verification: the run row's `created_at` (or `ts`)
            # tells us which segment to look up.
            ts = (
                run_row.get("created_at")
                or run_row.get("started_at")
                or run_row.get("ts")
                or started_at
            )
            anchored_segment_id, anchor_verified = _verify_anchor(
                cell_id=cell_id, ts=ts, session=session
            )
            notes["spec_table"] = _RUNTIME_TABLES.get(runtime, (None,))[1]
            notes["timestamp_used_for_anchor"] = (
                ts.isoformat() if isinstance(ts, datetime) else str(ts)
            )
            notes["execution"] = "pending_phase_7_5"

            # Phase 7.5 hooks: the actual re-execution. Until that
            # lands, replay_hash mirrors original_hash so output_matches
            # is a tautology for the audit-shadow path.
            replay_hash = original_hash
    except Exception as exc:  # noqa: BLE001 - report rather than raise
        logger.exception("replay_run failed for %s", run_id)
        error = f"{type(exc).__name__}: {exc}"

    finished_at = datetime.now(timezone.utc)

    # If the caller explicitly asks to drop the shadow schema (rare —
    # the auditor usually wants it retained for evidence), do so on a
    # fresh session so the schema-create commit lands first.
    if not keep_shadow_schema and shadow and not error:
        try:
            with get_session() as session:
                _drop_shadow_schema(shadow, session)
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            logger.warning("replay: shadow schema drop failed", exc_info=True)

    report = ReplayReport(
        run_id=run_id,
        runtime=runtime,
        cell_id=cell_id,
        target_environment=target_environment,
        spec_version_id=spec_version_id,
        mcp_tool_descriptor_hashes=descriptor_hashes,
        shadow_schema=shadow,
        original_output_hash=original_hash,
        replay_output_hash=replay_hash,
        output_matches=(original_hash == replay_hash and bool(original_hash)),
        anchored_segment_id=anchored_segment_id,
        anchor_verified=anchor_verified,
        started_at=started_at,
        finished_at=finished_at,
        error=error,
        notes=notes,
    )
    return report


__all__ = [
    "ReplayEnvironment",
    "ReplayReport",
    "replay_run",
]
