"""Iceberg-first data catalog endpoints.

Routes:

- ``GET    /datasets/namespaces`` — Iceberg namespace list.
- ``GET    /datasets/tables`` — combined Iceberg + ``DatasetCatalog`` listing.
- ``GET    /datasets/{namespace}/{name}`` — full table detail (schema,
  partitions, snapshots, llm annotations, column docs, sample).
- ``POST   /datasets/{namespace}/{name}/query`` — DuckDB-driven SQL
  preview (read-only).
- ``PATCH  /datasets/{namespace}/{name}`` — edit description / tags /
  column_docs.
- ``POST   /datasets/{namespace}/{name}/annotate`` — enqueue an
  annotation Celery task.
- ``DELETE /datasets/{namespace}/{name}`` — drop both Iceberg table and
  catalog row.
"""
from __future__ import annotations

import logging
import json
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.api.schemas import TaskAccepted
from aqp.data import iceberg_catalog
from aqp.data.iceberg_catalog import IcebergUnavailableError
from aqp.persistence.db import get_session
from aqp.persistence.models import DatasetCatalog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/datasets", tags=["datasets"])


_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|truncate|alter|create|copy|attach|detach|"
    r"export|grant|revoke|vacuum|pragma|set|call)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TableSummary(BaseModel):
    iceberg_identifier: str
    namespace: str
    name: str
    description: str | None = None
    domain: str | None = None
    tags: list[str] = Field(default_factory=list)
    load_mode: str = "managed"
    source_uri: str | None = None
    row_count: int | None = None
    file_count: int | None = None
    truncated: bool = False
    has_annotation: bool = False
    catalog_id: str | None = None
    location: str | None = None
    updated_at: datetime | None = None


class FieldDoc(BaseModel):
    id: int | None = None
    name: str
    type: str | None = None
    required: bool = False
    description: str | None = None
    pii: bool = False


class SnapshotEntry(BaseModel):
    snapshot_id: int
    parent_snapshot_id: int | None = None
    operation: str | None = None
    timestamp_ms: int
    summary: dict[str, str] = Field(default_factory=dict)


class TableDetail(TableSummary):
    fields: list[FieldDoc] = Field(default_factory=list)
    partition_spec: list[dict[str, Any]] = Field(default_factory=list)
    snapshots: list[SnapshotEntry] = Field(default_factory=list)
    llm_annotations: dict[str, Any] = Field(default_factory=dict)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class TablePatchRequest(BaseModel):
    description: str | None = None
    tags: list[str] | None = None
    column_docs: list[dict[str, Any]] | None = None
    domain: str | None = None


class TableQueryRequest(BaseModel):
    sql: str
    limit: int = Field(default=200, ge=1, le=10_000)


class AnnotateRequest(BaseModel):
    sample_rows: int = Field(default=25, ge=5, le=200)


class GroupingSuggestion(BaseModel):
    group_name: str
    members: list[str] = Field(default_factory=list)
    reason: str | None = None
    score: float = 0.5


class GroupingSuggestRequest(BaseModel):
    namespace: str | None = None
    names: list[str] = Field(default_factory=list)
    strategy: str = Field(default="heuristic", description="heuristic | llm")
    min_group_size: int = Field(default=2, ge=2, le=200)


class GroupingApplyRequest(BaseModel):
    groups: list[GroupingSuggestion] = Field(default_factory=list)
    dry_run: bool = False


class GroupingConsolidateRequest(BaseModel):
    """Physically merge ``members`` into a single Iceberg table at ``group_name``.

    ``confirm`` must be explicitly ``True`` for any non-dry-run that drops the
    member tables; the API raises 400 otherwise to make destructive operations
    a deliberate two-step.
    """

    group_name: str = Field(..., description="Target identifier 'namespace.name'.")
    members: list[str] = Field(..., min_length=2)
    dry_run: bool = True
    drop_members: bool = True
    confirm: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split(namespace: str, name: str) -> str:
    if not namespace or not name:
        raise HTTPException(400, "namespace and name are required")
    return f"{namespace}.{name}"


def _catalog_row_for(identifier: str) -> DatasetCatalog | None:
    try:
        with get_session() as session:
            return session.execute(
                select(DatasetCatalog)
                .where(DatasetCatalog.iceberg_identifier == identifier)
                .limit(1)
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        logger.debug("catalog lookup failed for %s", identifier, exc_info=True)
        return None


def _summary_from_catalog(
    identifier: str,
    catalog_row: DatasetCatalog | None,
    metadata: dict[str, Any] | None,
) -> TableSummary:
    ns, _, name = identifier.rpartition(".")
    annotations: dict[str, Any] = (catalog_row.llm_annotations or {}) if catalog_row else {}
    description = ""
    domain = ""
    tags: list[str] = []
    if catalog_row is not None:
        description = annotations.get("description") or catalog_row.description or ""
        domain = catalog_row.domain or annotations.get("domain") or ""
        tags = list(catalog_row.tags or [])
    return TableSummary(
        iceberg_identifier=identifier,
        namespace=ns,
        name=name,
        description=description or None,
        domain=domain or None,
        tags=tags,
        load_mode=(catalog_row.load_mode if catalog_row else "managed"),
        source_uri=(catalog_row.source_uri if catalog_row else None),
        row_count=(int((catalog_row.meta or {}).get("row_count", 0)) if catalog_row else None),
        file_count=(int((catalog_row.meta or {}).get("file_count", 0)) if catalog_row else None),
        truncated=bool((catalog_row.meta or {}).get("truncated", False)) if catalog_row else False,
        has_annotation=bool(annotations.get("description")),
        catalog_id=catalog_row.id if catalog_row else None,
        location=(metadata or {}).get("location"),
        updated_at=(catalog_row.updated_at if catalog_row else None),
    )


def _ensure_catalog_loadable() -> None:
    try:
        iceberg_catalog.get_catalog()
    except IcebergUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"iceberg catalog unavailable: {exc}") from exc


def _base_group_name(name: str) -> str:
    candidate = str(name or "").strip().lower()
    if not candidate:
        return candidate
    patterns = [
        r"(.+?)(?:[_-]part[_-]?\d+)$",
        r"(.+?)(?:[_-](?:chunk|slice|shard)[_-]?\d+)$",
        r"(.+?)(?:[_-]\d{1,4}of\d{1,4})$",
        r"(.+?)(?:[_-](?:p|pt|batch)[_-]?\d+)$",
    ]
    for pat in patterns:
        m = re.match(pat, candidate)
        if m:
            return m.group(1)
    m2 = re.match(r"(.+?)(?:[_-]\d{2,})$", candidate)
    if m2:
        return m2.group(1)
    return candidate


def _heuristic_grouping(identifiers: list[str], min_group_size: int) -> list[GroupingSuggestion]:
    buckets: dict[str, list[str]] = {}
    for ident in identifiers:
        _, _, table = ident.rpartition(".")
        key = _base_group_name(table)
        if not key or key == table.lower():
            continue
        buckets.setdefault(key, []).append(ident)
    out: list[GroupingSuggestion] = []
    for key, members in sorted(buckets.items()):
        if len(members) < min_group_size:
            continue
        namespace = members[0].split(".", 1)[0] if "." in members[0] else ""
        group_name = f"{namespace}.{key}" if namespace else key
        out.append(
            GroupingSuggestion(
                group_name=group_name,
                members=sorted(set(members)),
                reason="heuristic name-family grouping",
                score=min(0.99, 0.4 + 0.1 * len(members)),
            )
        )
    return out


def _llm_grouping(identifiers: list[str], min_group_size: int) -> list[GroupingSuggestion]:
    from aqp.llm.providers.router import router_complete
    from aqp.runtime.control_plane import get_provider_control

    control = get_provider_control()
    provider = str(control.get("provider") or "ollama")
    model = str(control.get("quick_model") or control.get("deep_model") or "")
    if not model:
        raise RuntimeError("provider control has no model configured")
    prompt = (
        "Group these dataset table identifiers into logical families where each family has at least "
        f"{min_group_size} members. Return strict JSON with shape "
        '{"groups":[{"group_name":"ns.family","members":["ns.t1"],"reason":"...","score":0.0}]}. '
        f"Identifiers: {identifiers!r}"
    )
    response = router_complete(provider=provider, model=model, prompt=prompt, temperature=0.0)
    text = response.content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("LLM grouping response is not JSON")
    payload = json.loads(text[start : end + 1])
    groups = payload.get("groups") if isinstance(payload, dict) else []
    out: list[GroupingSuggestion] = []
    if isinstance(groups, list):
        for raw in groups:
            if not isinstance(raw, dict):
                continue
            suggestion = GroupingSuggestion(
                group_name=str(raw.get("group_name") or "").strip(),
                members=[str(m) for m in (raw.get("members") or []) if str(m).strip()],
                reason=str(raw.get("reason") or "llm suggestion"),
                score=float(raw.get("score") or 0.5),
            )
            if suggestion.group_name and len(suggestion.members) >= min_group_size:
                out.append(suggestion)
    return out


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/namespaces")
def list_namespaces() -> dict[str, Any]:
    _ensure_catalog_loadable()
    try:
        items = iceberg_catalog.list_namespaces()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"iceberg list_namespaces failed: {exc}") from exc
    return {"namespaces": items}


@router.get("/tables", response_model=list[TableSummary])
def list_tables(namespace: str | None = None) -> list[TableSummary]:
    _ensure_catalog_loadable()
    try:
        identifiers = iceberg_catalog.list_tables(namespace)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"iceberg list_tables failed: {exc}") from exc

    catalog_rows: dict[str, DatasetCatalog] = {}
    try:
        with get_session() as session:
            stmt = select(DatasetCatalog).where(DatasetCatalog.iceberg_identifier.is_not(None))
            for row in session.execute(stmt).scalars().all():
                if row.iceberg_identifier:
                    catalog_rows[row.iceberg_identifier] = row
    except Exception:  # noqa: BLE001
        logger.debug("catalog batch lookup failed", exc_info=True)

    out: list[TableSummary] = []
    for identifier in identifiers:
        out.append(_summary_from_catalog(identifier, catalog_rows.get(identifier), None))

    # Surface catalog rows that are referenced but missing from Iceberg
    # (e.g. table dropped under us); these still show up so users can
    # delete the stale row from the UI.
    missing = set(catalog_rows) - set(identifiers)
    for identifier in sorted(missing):
        if namespace and not identifier.startswith(f"{namespace}."):
            continue
        summary = _summary_from_catalog(identifier, catalog_rows[identifier], None)
        summary.location = None
        out.append(summary)
    return out


@router.get("/groups")
def list_groups(namespace: str | None = None) -> dict[str, Any]:
    groups: dict[str, list[str]] = {}
    with get_session() as session:
        stmt = select(DatasetCatalog).where(DatasetCatalog.iceberg_identifier.is_not(None))
        rows = session.execute(stmt).scalars().all()
    for row in rows:
        ident = str(row.iceberg_identifier or "").strip()
        if not ident:
            continue
        if namespace and not ident.startswith(f"{namespace}."):
            continue
        meta = dict(row.meta or {})
        group_name = str(meta.get("group_name") or "").strip()
        if not group_name:
            continue
        groups.setdefault(group_name, []).append(ident)
    return {
        "groups": [
            {"group_name": g, "members": sorted(members), "count": len(members)}
            for g, members in sorted(groups.items())
        ]
    }


@router.post("/grouping/propose")
def propose_groups(req: GroupingSuggestRequest) -> dict[str, Any]:
    _ensure_catalog_loadable()
    identifiers = iceberg_catalog.list_tables(req.namespace)
    if req.names:
        wanted = {str(n).strip() for n in req.names if str(n).strip()}
        identifiers = [i for i in identifiers if i in wanted or i.rpartition(".")[2] in wanted]
    if req.strategy.lower() == "llm":
        try:
            groups = _llm_grouping(identifiers, req.min_group_size)
        except Exception:
            logger.warning("llm grouping failed; falling back to heuristic", exc_info=True)
            groups = _heuristic_grouping(identifiers, req.min_group_size)
    else:
        groups = _heuristic_grouping(identifiers, req.min_group_size)
    return {
        "namespace": req.namespace,
        "strategy": req.strategy,
        "groups": [g.model_dump() for g in groups],
        "count": len(groups),
    }


@router.post("/grouping/consolidate", response_model=TaskAccepted)
def consolidate_grouping(req: GroupingConsolidateRequest) -> TaskAccepted:
    """Schedule a physical Iceberg consolidation Celery task.

    For dry-runs (``dry_run=true``) the ``confirm`` flag is unused.
    For non-dry-runs ``confirm`` MUST be ``true`` to authorise dropping the
    member tables.
    """
    members = [str(m).strip() for m in req.members if str(m).strip()]
    if len(members) < 2:
        raise HTTPException(400, "consolidation requires at least 2 members")
    target = (req.group_name or "").strip()
    if not target or "." not in target:
        raise HTTPException(400, "group_name must be 'namespace.name'")
    if not req.dry_run and req.drop_members and not req.confirm:
        raise HTTPException(
            400,
            "non-dry-run consolidation that drops members requires confirm=true",
        )
    from aqp.tasks.ingestion_tasks import consolidate_iceberg_group

    async_result = consolidate_iceberg_group.delay(
        group_name=target,
        members=members,
        dry_run=req.dry_run,
        drop_members=req.drop_members,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.post("/grouping/apply")
def apply_groups(req: GroupingApplyRequest) -> dict[str, Any]:
    if not req.groups:
        raise HTTPException(400, "at least one group is required")
    payload: list[dict[str, Any]] = []
    with get_session() as session:
        for group in req.groups:
            members = [str(m).strip() for m in group.members if str(m).strip()]
            if not members:
                continue
            rows = session.execute(
                select(DatasetCatalog).where(DatasetCatalog.iceberg_identifier.in_(members))
            ).scalars().all()
            if not rows:
                continue
            for row in rows:
                meta = dict(row.meta or {})
                meta["group_name"] = group.group_name
                meta["group_score"] = float(group.score)
                meta["group_reason"] = group.reason or "manual grouping"
                row.meta = meta
                tags = list(row.tags or [])
                if "grouped" not in tags:
                    tags.append("grouped")
                row.tags = tags
                row.updated_at = datetime.utcnow()
            payload.append(
                {
                    "group_name": group.group_name,
                    "members": sorted(set(members)),
                    "matched_rows": len(rows),
                    "reason": group.reason,
                    "score": group.score,
                }
            )
        if not req.dry_run:
            session.flush()
    return {
        "dry_run": req.dry_run,
        "groups_applied": len(payload),
        "groups": payload,
    }


@router.get("/{namespace}/{name}/preview-bars")
def preview_bars(
    namespace: str,
    name: str,
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Lightweight bars-shape probe over an Iceberg table.

    Returns ``{n_rows, min_ts, max_ts, vt_symbols, columns}`` derived
    from the underlying Parquet plan files via DuckDB. Used by the
    backtest wizard to validate a candidate data source before commit.
    """
    _ensure_catalog_loadable()
    identifier = _split(namespace, name)

    try:
        import duckdb

        conn = duckdb.connect(":memory:", read_only=False)
        try:
            view_name = iceberg_catalog.iceberg_to_duckdb_view(conn, identifier)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"duckdb could not read Iceberg files: {exc}") from exc
        if not view_name:
            raise HTTPException(404, f"table {identifier!r} has no data files yet")

        info = conn.execute(f'PRAGMA table_info("{view_name}")').fetchdf()
        cols = {str(c).lower(): str(c) for c in info["name"].tolist()}
        columns = list(info["name"].tolist())

        ts_col = next((cols[k] for k in ("timestamp", "ts", "datetime", "date") if k in cols), None)
        sym_col = next(
            (cols[k] for k in ("vt_symbol", "symbol", "ticker", "instrument") if k in cols),
            None,
        )

        select_pieces: list[str] = ["COUNT(*) AS n_rows"]
        if ts_col:
            select_pieces.append(f'MIN("{ts_col}") AS min_ts, MAX("{ts_col}") AS max_ts')
        if sym_col:
            select_pieces.append(f'COUNT(DISTINCT "{sym_col}") AS n_symbols')

        where: list[str] = []
        args: list[Any] = []
        if ts_col and start:
            where.append(f'"{ts_col}" >= ?')
            args.append(start)
        if ts_col and end:
            where.append(f'"{ts_col}" <= ?')
            args.append(end)
        sql = f'SELECT {", ".join(select_pieces)} FROM "{view_name}"'
        if where:
            sql += " WHERE " + " AND ".join(where)
        agg = conn.execute(sql, args).fetchone()

        symbol_sample: list[str] = []
        if sym_col:
            sym_sql = f'SELECT DISTINCT "{sym_col}" FROM "{view_name}"'
            if where:
                sym_sql += " WHERE " + " AND ".join(where)
            sym_sql += f' ORDER BY "{sym_col}" LIMIT 200'
            symbol_sample = [
                str(r[0]) for r in conn.execute(sym_sql, args).fetchall() if r and r[0] is not None
            ]
    except IcebergUnavailableError as exc:  # pragma: no cover
        raise HTTPException(503, str(exc)) from exc

    n_rows = int(agg[0]) if agg and agg[0] is not None else 0
    min_ts = str(agg[1]) if agg and len(agg) > 1 and agg[1] is not None else None
    max_ts = str(agg[2]) if agg and len(agg) > 2 and agg[2] is not None else None
    n_symbols = int(agg[3]) if agg and len(agg) > 3 and agg[3] is not None else None

    return {
        "iceberg_identifier": identifier,
        "n_rows": n_rows,
        "min_ts": min_ts,
        "max_ts": max_ts,
        "n_symbols": n_symbols,
        "vt_symbols": symbol_sample,
        "columns": columns,
        "timestamp_column": ts_col,
        "symbol_column": sym_col,
    }


@router.get("/{namespace}/{name}", response_model=TableDetail)
def table_detail(namespace: str, name: str, sample_rows: int = 50) -> TableDetail:
    _ensure_catalog_loadable()
    identifier = _split(namespace, name)
    metadata = iceberg_catalog.table_metadata(identifier)
    catalog_row = _catalog_row_for(identifier)
    summary = _summary_from_catalog(identifier, catalog_row, metadata)

    fields: list[FieldDoc] = []
    column_docs = (catalog_row.column_docs if catalog_row else []) or []
    docs_by_name = {(d or {}).get("name"): d for d in column_docs if isinstance(d, dict)}
    for f in metadata.get("fields", []):
        doc = docs_by_name.get(f["name"]) or {}
        fields.append(
            FieldDoc(
                id=int(f["id"]) if f.get("id") is not None else None,
                name=f["name"],
                type=str(f.get("type") or ""),
                required=bool(f.get("required")),
                description=str(doc.get("description") or "") or None,
                pii=bool(doc.get("pii")),
            )
        )

    snapshots = [SnapshotEntry(**snap) for snap in iceberg_catalog.snapshot_history(identifier)]
    sample_payload: list[dict[str, Any]] = []
    arrow = iceberg_catalog.read_arrow(identifier, limit=max(1, min(int(sample_rows), 500)))
    if arrow is not None and arrow.num_rows:
        try:
            sample_payload = arrow.to_pylist()
        except Exception:  # noqa: BLE001
            sample_payload = []

    return TableDetail(
        **summary.model_dump(),
        fields=fields,
        partition_spec=metadata.get("partition_spec", []),
        snapshots=snapshots,
        llm_annotations=(catalog_row.llm_annotations if catalog_row else {}) or {},
        sample_rows=sample_payload,
    )


@router.post("/{namespace}/{name}/query")
def query_table(namespace: str, name: str, req: TableQueryRequest) -> dict[str, Any]:
    _ensure_catalog_loadable()
    identifier = _split(namespace, name)
    sql = (req.sql or "").strip().rstrip(";")
    if not sql:
        raise HTTPException(400, "sql is required")
    if _FORBIDDEN_SQL.search(sql):
        raise HTTPException(400, "DDL/DML statements are not permitted")

    try:
        import duckdb

        conn = duckdb.connect(":memory:", read_only=False)
        try:
            view_name = iceberg_catalog.iceberg_to_duckdb_view(conn, identifier)
        except Exception as exc:  # noqa: BLE001
            logger.warning("duckdb view registration failed for %s", identifier, exc_info=True)
            raise HTTPException(400, f"duckdb could not read Iceberg data files: {exc}") from exc
        if not view_name:
            raise HTTPException(404, f"table {identifier!r} has no data files yet")
        rewritten = _rewrite_query_table_refs(sql, namespace, name, view_name)
        full_sql = f"SELECT * FROM ({rewritten}) AS _q LIMIT {int(req.limit)}"
        try:
            df = conn.execute(full_sql).df()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"duckdb error: {exc}") from exc
    except IcebergUnavailableError as exc:  # pragma: no cover
        raise HTTPException(503, str(exc)) from exc

    return {
        "rows": df.to_dict(orient="records"),
        "count": int(len(df)),
        "columns": list(df.columns),
    }


def _rewrite_query_table_refs(sql: str, namespace: str, name: str, view_name: str) -> str:
    """Allow users to query ``table``, ``name`` or ``namespace.name`` aliases."""
    replacements = [
        (rf"(?<![\w.]){re.escape(namespace)}\.{re.escape(name)}(?![\w.])", view_name),
        (rf"\b{re.escape(name)}\b", view_name),
        (r"\btable\b", view_name),
    ]
    rewritten = sql
    for pattern, replacement in replacements:
        rewritten = re.sub(pattern, replacement, rewritten, flags=re.IGNORECASE)
    return rewritten


@router.patch("/{namespace}/{name}", response_model=TableSummary)
def patch_table(namespace: str, name: str, req: TablePatchRequest) -> TableSummary:
    identifier = _split(namespace, name)
    with get_session() as session:
        row = session.execute(
            select(DatasetCatalog)
            .where(DatasetCatalog.iceberg_identifier == identifier)
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, f"no catalog row for {identifier!r}")
        if req.description is not None:
            row.description = req.description
            row.llm_annotations = {**(row.llm_annotations or {}), "description": req.description}
        if req.tags is not None:
            row.tags = list(req.tags)
        if req.column_docs is not None:
            row.column_docs = list(req.column_docs)
        if req.domain is not None:
            row.domain = req.domain
        row.updated_at = datetime.utcnow()
        session.add(row)
        session.flush()
    metadata = iceberg_catalog.table_metadata(identifier)
    catalog_row = _catalog_row_for(identifier)
    return _summary_from_catalog(identifier, catalog_row, metadata)


@router.post("/{namespace}/{name}/annotate", response_model=TaskAccepted)
def annotate(namespace: str, name: str, req: AnnotateRequest) -> TaskAccepted:
    _ensure_catalog_loadable()
    identifier = _split(namespace, name)
    if iceberg_catalog.load_table(identifier) is None:
        raise HTTPException(404, f"table {identifier!r} not found")
    from aqp.tasks.ingestion_tasks import annotate_dataset

    async_result = annotate_dataset.delay(identifier, None, False, int(req.sample_rows))
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.delete("/{namespace}/{name}")
def delete_table(namespace: str, name: str) -> dict[str, Any]:
    _ensure_catalog_loadable()
    identifier = _split(namespace, name)
    dropped = iceberg_catalog.drop_table(identifier)
    deleted_rows = 0
    try:
        with get_session() as session:
            stmt = select(DatasetCatalog).where(DatasetCatalog.iceberg_identifier == identifier)
            for row in session.execute(stmt).scalars().all():
                session.delete(row)
                deleted_rows += 1
            session.flush()
    except Exception:  # noqa: BLE001
        logger.warning("catalog delete failed for %s", identifier, exc_info=True)
    return {
        "iceberg_identifier": identifier,
        "iceberg_dropped": bool(dropped),
        "catalog_rows_deleted": int(deleted_rows),
    }
