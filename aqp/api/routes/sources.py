"""Unified endpoint for the ``data_sources`` registry.

Every AQP data source (yfinance, Polygon, Alpha Vantage, IBKR, local
files, FRED, SEC EDGAR, GDelt, Alpaca, CCXT) has a row in
``data_sources`` — this module exposes that registry over REST so the
UI can render a live Sources Explorer, probe adapters for reachability,
and toggle enabled/disabled without touching YAML.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from aqp.config import settings
from aqp.data.sources.base import ProbeResult
from aqp.data.sources.registry import (
    get_data_source,
    list_data_sources,
    set_data_source_enabled,
    upsert_data_source,
)
from aqp.data.sources.setup_wizards import (
    SourceSetupWizard,
    WIZARDS,
    get_wizard,
    list_wizards,
)
from aqp.persistence.db import get_session
from aqp.persistence.models_data_control import SourceLibraryEntry, SourceMetadataVersion

router = APIRouter(prefix="/sources", tags=["sources"])


class DataSourceSummary(BaseModel):
    id: str
    name: str
    display_name: str
    kind: str
    vendor: str | None = None
    auth_type: str
    base_url: str | None = None
    protocol: str
    capabilities: dict[str, Any] = Field(default_factory=dict)
    rate_limits: dict[str, Any] = Field(default_factory=dict)
    credentials_ref: str | None = None
    enabled: bool
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ToggleRequest(BaseModel):
    enabled: bool


class SourceEditRequest(BaseModel):
    display_name: str | None = None
    kind: str | None = None
    vendor: str | None = None
    auth_type: str | None = None
    base_url: str | None = None
    protocol: str | None = None
    capabilities: dict[str, Any] | None = None
    rate_limits: dict[str, Any] | None = None
    credentials_ref: str | None = None
    enabled: bool | None = None
    meta: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    import_uri: str | None = None
    reference_path: str | None = None
    docs_url: str | None = None
    default_node: str | None = None
    setup_steps: list[dict[str, Any]] = Field(default_factory=list)
    pipeline_hints: dict[str, Any] = Field(default_factory=dict)


class SourceImportRequest(SourceEditRequest):
    name: str
    raw_source_url: str | None = None
    uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceLibraryView(BaseModel):
    id: str
    source_name: str
    display_name: str
    import_uri: str | None = None
    reference_path: str | None = None
    docs_url: str | None = None
    default_node: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    setup_steps: list[dict[str, Any]] = Field(default_factory=list)
    pipeline_hints: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    version: int = 1
    enabled: bool = True
    updated_at: datetime


class SourceMetadataVersionView(BaseModel):
    id: str
    source_name: str
    version: int
    change_kind: str
    import_uri: str | None = None
    reference_path: str | None = None
    docs_url: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_by: str
    created_at: datetime


class ProbeResponse(BaseModel):
    name: str
    ok: bool
    message: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class CredentialEntry(BaseModel):
    key: str
    value: str = ""
    configured: bool = False
    used_by: list[str] = Field(default_factory=list)


class CredentialsResponse(BaseModel):
    env_file: str
    credentials: list[CredentialEntry] = Field(default_factory=list)


class CredentialsUpdateRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class CredentialsUpdateResponse(BaseModel):
    env_file: str
    updated: list[str] = Field(default_factory=list)


_ADAPTERS: dict[str, str] = {
    # source_name -> "module:Class"
    "fred": "aqp.data.sources.fred.series:FredSeriesAdapter",
    "sec_edgar": "aqp.data.sources.sec.filings:SecFilingsAdapter",
    "gdelt": "aqp.data.sources.gdelt.adapter:GDeltAdapter",
}


class _AlphaVantageProbeAdapter:
    """Runtime probe adapter backed by the rich AQP Alpha Vantage client."""

    symbol = "IBM"
    env_key = "AQP_ALPHA_VANTAGE_API_KEY"

    def probe(self) -> ProbeResult:
        from aqp.data.sources.alpha_vantage import AlphaVantageClient
        from aqp.data.sources.alpha_vantage._errors import RateLimitError

        started = perf_counter()
        try:
            client = AlphaVantageClient()
            try:
                quote = client.timeseries.global_quote(self.symbol)
            finally:
                client.close()
        except RateLimitError as exc:
            return ProbeResult.success(
                "alpha_vantage reachable (rate limited)",
                latency_ms=round((perf_counter() - started) * 1000.0, 2),
                note=str(exc),
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            )
        except Exception as exc:
            return ProbeResult.failure(f"alpha_vantage probe failed: {exc}")
        latency_ms = round((perf_counter() - started) * 1000.0, 2)
        payload = quote.model_dump()
        if payload:
            return ProbeResult.success(
                "alpha_vantage reachable",
                latency_ms=latency_ms,
                symbol=payload.get("symbol") or self.symbol,
            )
        return ProbeResult.failure("unexpected alpha_vantage response payload", latency_ms=latency_ms)


_CREDENTIAL_ALIASES: dict[str, str] = {
    # Legacy wording in a few seeded/fallback rows.
    "AQP_ALPACA_KEY_ID": "AQP_ALPACA_API_KEY",
}

_EXTRA_CREDENTIAL_KEYS: dict[str, set[str]] = {
    # Complements explicit source refs and keeps the config page practical.
    "AQP_ALPACA_SECRET_KEY": {"alpaca"},
    "AQP_GDELT_BIGQUERY_PROJECT": {"gdelt"},
    "GOOGLE_APPLICATION_CREDENTIALS": {"gdelt"},
}

_SETTINGS_BINDINGS: dict[str, str] = {
    "AQP_ALPHA_VANTAGE_API_KEY": "alpha_vantage_api_key",
    "AQP_FRED_API_KEY": "fred_api_key",
    "AQP_SEC_EDGAR_IDENTITY": "sec_edgar_identity",
    "AQP_ALPACA_API_KEY": "alpaca_api_key",
    "AQP_ALPACA_SECRET_KEY": "alpaca_secret_key",
    "AQP_IBKR_HOST": "ibkr_host",
    "AQP_IBKR_PORT": "ibkr_port",
    "AQP_GDELT_BIGQUERY_PROJECT": "gdelt_bigquery_project",
}


def _canonical_credential_key(raw: str) -> str:
    key = str(raw or "").strip()
    return _CREDENTIAL_ALIASES.get(key, key)


def _extract_credential_keys(raw_ref: str | None) -> list[str]:
    if not raw_ref:
        return []
    keys: list[str] = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(raw_ref)):
        key = _canonical_credential_key(token)
        if not key:
            continue
        if key.startswith("AQP_") or key.startswith("GOOGLE_"):
            keys.append(key)
    return keys


def _credential_key_index() -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    rows = list_data_sources()
    for row in rows:
        source_name = str(row.get("name") or "")
        for key in _extract_credential_keys(row.get("credentials_ref")):
            index.setdefault(key, set()).add(source_name)
    for key, sources in _EXTRA_CREDENTIAL_KEYS.items():
        index.setdefault(key, set()).update(set(sources))
    return index


def _env_file_path() -> Path:
    raw = settings.model_config.get("env_file", ".env")
    if isinstance(raw, (tuple, list)):
        raw = raw[0] if raw else ".env"
    env_path = Path(str(raw or ".env"))
    if not env_path.is_absolute():
        env_path = Path.cwd() / env_path
    return env_path.resolve()


def _decode_env_value(raw: str) -> str:
    value = str(raw).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        unquoted = value[1:-1]
        if value[0] == '"':
            return unquoted.replace("\\\\", "\\").replace('\\"', '"')
        return unquoted
    return value


def _encode_env_value(value: str) -> str:
    raw = str(value)
    if raw == "":
        return ""
    needs_quotes = any(ch.isspace() for ch in raw) or "#" in raw or '"' in raw
    if not needs_quotes:
        return raw
    escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _read_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _decode_env_value(raw)
    return values


def _write_env_values(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    index_by_key: dict[str, int] = {}
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key and key not in index_by_key:
            index_by_key[key] = idx

    for key, value in updates.items():
        encoded = _encode_env_value(value)
        rendered = f"{key}={encoded}"
        if key in index_by_key:
            lines[index_by_key[key]] = rendered
        else:
            lines.append(rendered)

    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines).rstrip()
    path.write_text(f"{content}\n" if content else "", encoding="utf-8")


def _coerce_runtime_value(current: Any, raw: str) -> Any:
    if isinstance(current, bool):
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    return raw


def _apply_runtime_credentials(values: dict[str, str]) -> None:
    for key, value in values.items():
        os.environ[key] = value
        setting_attr = _SETTINGS_BINDINGS.get(key)
        if not setting_attr or not hasattr(settings, setting_attr):
            continue
        current = getattr(settings, setting_attr)
        try:
            coerced = _coerce_runtime_value(current, value)
        except Exception:
            coerced = value
        try:
            setattr(settings, setting_attr, coerced)
        except Exception:
            # Best effort only; process env is still updated.
            continue


def _load_adapter(name: str) -> Any | None:
    if name == "alpha_vantage":
        return _AlphaVantageProbeAdapter()
    spec = _ADAPTERS.get(name)
    if not spec:
        return None
    module_path, _, class_name = spec.partition(":")
    try:
        module = __import__(module_path, fromlist=[class_name])
        cls = getattr(module, class_name)
        return cls()
    except Exception:  # pragma: no cover — adapter optional deps
        return None


def _infer_default_node(uri: str | None, reference_path: str | None = None) -> str:
    raw = (uri or reference_path or "").strip().lower()
    if raw.startswith(("http://", "https://")):
        if raw.endswith((".zip", ".tar", ".tar.gz", ".tgz")):
            return "source.archive"
        return "source.http"
    if raw.startswith(("s3://", "minio://")):
        return "source.s3"
    if raw.startswith("gs://"):
        return "source.gcs"
    if raw.startswith(("az://", "abfs://", "azure://")):
        return "source.azure_blob"
    if raw and Path(raw).suffix:
        return "source.local_file"
    return "source.local_directory" if raw else "source.rest_api"


def _source_library_view(row: SourceLibraryEntry) -> SourceLibraryView:
    return SourceLibraryView(
        id=row.id,
        source_name=row.source_name,
        display_name=row.display_name,
        import_uri=row.import_uri,
        reference_path=row.reference_path,
        docs_url=row.docs_url,
        default_node=row.default_node,
        metadata_json=dict(row.metadata_json or {}),
        setup_steps=[dict(item) for item in (row.setup_steps or [])],
        pipeline_hints=dict(row.pipeline_hints or {}),
        tags=list(row.tags or []),
        version=int(row.version or 1),
        enabled=bool(row.enabled),
        updated_at=row.updated_at or datetime.utcnow(),
    )


def _version_view(row: SourceMetadataVersion) -> SourceMetadataVersionView:
    return SourceMetadataVersionView(
        id=row.id,
        source_name=row.source_name,
        version=int(row.version or 1),
        change_kind=row.change_kind,
        import_uri=row.import_uri,
        reference_path=row.reference_path,
        docs_url=row.docs_url,
        metadata_json=dict(row.metadata_json or {}),
        tags=list(row.tags or []),
        created_by=row.created_by,
        created_at=row.created_at or datetime.utcnow(),
    )


def _persist_source_library(
    *,
    source: dict[str, Any],
    req: SourceEditRequest,
    change_kind: str,
) -> SourceLibraryView | None:
    try:
        source_name = str(source.get("name") or "")
        if not source_name:
            return None
        import_uri = req.import_uri or getattr(req, "raw_source_url", None) or getattr(req, "uri", None) or req.base_url
        reference_path = req.reference_path
        metadata = {
            **dict(source.get("meta") or {}),
            **dict(getattr(req, "metadata", {}) or {}),
            **dict(req.meta or {}),
            "source": {
                "kind": source.get("kind"),
                "vendor": source.get("vendor"),
                "base_url": source.get("base_url"),
                "protocol": source.get("protocol"),
                "capabilities": source.get("capabilities") or {},
            },
        }
        with get_session() as session:
            current_version = (
                session.execute(
                    select(func.max(SourceMetadataVersion.version)).where(
                        SourceMetadataVersion.source_name == source_name
                    )
                ).scalar_one()
                or 0
            )
            version = int(current_version) + 1
            entry = session.execute(
                select(SourceLibraryEntry)
                .where(SourceLibraryEntry.source_name == source_name)
                .limit(1)
            ).scalar_one_or_none()
            if entry is None:
                entry = SourceLibraryEntry(source_name=source_name, display_name=source.get("display_name") or source_name)
            entry.source_id = source.get("id")
            entry.display_name = req.display_name or source.get("display_name") or source_name
            entry.import_uri = import_uri
            entry.reference_path = reference_path
            entry.docs_url = req.docs_url or metadata.get("documentation_url")
            entry.default_node = req.default_node or _infer_default_node(import_uri, reference_path)
            entry.metadata_json = metadata
            entry.setup_steps = list(req.setup_steps or _default_setup_steps(source_name, source))
            entry.pipeline_hints = dict(req.pipeline_hints or _default_pipeline_hints(source, entry.default_node))
            entry.tags = list(req.tags or metadata.get("tags") or [])
            entry.version = version
            entry.enabled = bool(source.get("enabled", True))
            entry.updated_at = datetime.utcnow()
            session.add(entry)

            snapshot = SourceMetadataVersion(
                source_id=source.get("id"),
                source_name=source_name,
                version=version,
                change_kind=change_kind,
                import_uri=import_uri,
                reference_path=reference_path,
                docs_url=entry.docs_url,
                metadata_json=metadata,
                tags=list(entry.tags or []),
            )
            session.add(snapshot)
            session.flush()
            return _source_library_view(entry)
    except Exception:  # noqa: BLE001
        return None


def _default_setup_steps(source_name: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = [
        {"id": "review-metadata", "label": "Review source metadata", "status": "pending"},
    ]
    credentials_ref = source.get("credentials_ref")
    if credentials_ref:
        steps.append(
            {
                "id": "configure-credentials",
                "label": f"Configure {credentials_ref}",
                "status": "pending",
                "secret_ref": credentials_ref,
            }
        )
    steps.append({"id": "probe", "label": f"Probe {source_name}", "status": "pending"})
    steps.append({"id": "attach-pipeline", "label": "Attach or create a pipeline manifest", "status": "pending"})
    return steps


def _default_pipeline_hints(source: dict[str, Any], default_node: str | None) -> dict[str, Any]:
    return {
        "default_node": default_node,
        "source_name": source.get("name"),
        "capabilities": source.get("capabilities") or {},
        "suggested_sinks": ["sink.iceberg", "sink.parquet", "sink.profile"],
    }


@router.get("", response_model=list[DataSourceSummary])
def list_sources(enabled_only: bool = False) -> list[DataSourceSummary]:
    return [DataSourceSummary(**row) for row in list_data_sources(enabled_only=enabled_only)]


@router.get("/library", response_model=list[SourceLibraryView])
def list_source_library() -> list[SourceLibraryView]:
    with get_session() as session:
        rows = session.execute(
            select(SourceLibraryEntry).order_by(SourceLibraryEntry.source_name)
        ).scalars().all()
        return [_source_library_view(row) for row in rows]


@router.post("/import", response_model=DataSourceSummary)
def import_source(req: SourceImportRequest) -> DataSourceSummary:
    name = req.name.strip().lower().replace(" ", "_").replace("-", "_")
    if not name:
        raise HTTPException(status_code=400, detail="source name is required")
    import_uri = req.raw_source_url or req.uri or req.import_uri or req.base_url
    metadata = dict(req.metadata or {})
    capabilities = {
        **dict(req.capabilities or {}),
        "pipelines": {
            "default_node": req.default_node or _infer_default_node(import_uri, req.reference_path),
            "import_uri": import_uri,
            "reference_path": req.reference_path,
        },
    }
    row = upsert_data_source(
        name=name,
        display_name=req.display_name or metadata.get("display_name") or name,
        kind=req.kind or metadata.get("kind") or ("local_file" if req.reference_path else "rest_api"),
        vendor=req.vendor or metadata.get("vendor"),
        auth_type=req.auth_type or metadata.get("auth_type") or "none",
        base_url=req.base_url or req.raw_source_url or metadata.get("base_url"),
        protocol=req.protocol or metadata.get("protocol") or ("file" if req.reference_path else "https/json"),
        capabilities=capabilities,
        rate_limits=req.rate_limits or metadata.get("rate_limits"),
        credentials_ref=req.credentials_ref or metadata.get("credentials_ref"),
        enabled=req.enabled,
        meta={
            **metadata,
            **dict(req.meta or {}),
            "import_uri": import_uri,
            "reference_path": req.reference_path,
            "docs_url": req.docs_url,
        },
    )
    _persist_source_library(source=row, req=req, change_kind="import")
    return DataSourceSummary(**row)


@router.get("/credentials", response_model=CredentialsResponse)
def list_credentials() -> CredentialsResponse:
    env_path = _env_file_path()
    env_values = _read_env_values(env_path)
    index = _credential_key_index()
    entries: list[CredentialEntry] = []
    for key in sorted(index):
        value = str(os.environ.get(key, env_values.get(key, "")) or "")
        entries.append(
            CredentialEntry(
                key=key,
                value=value,
                configured=bool(value.strip()),
                used_by=sorted(index[key]),
            )
        )
    return CredentialsResponse(env_file=str(env_path), credentials=entries)


@router.put("/credentials", response_model=CredentialsUpdateResponse)
def update_credentials(req: CredentialsUpdateRequest) -> CredentialsUpdateResponse:
    env_path = _env_file_path()
    allowed = set(_credential_key_index())
    updates: dict[str, str] = {}
    for raw_key, raw_value in (req.values or {}).items():
        key = _canonical_credential_key(raw_key)
        if not key:
            continue
        if key not in allowed and not (key.startswith("AQP_") or key.startswith("GOOGLE_")):
            continue
        updates[key] = str(raw_value or "")

    if updates:
        _write_env_values(env_path, updates)
        _apply_runtime_credentials(updates)

    return CredentialsUpdateResponse(
        env_file=str(env_path),
        updated=sorted(updates.keys()),
    )


@router.get("/{name}", response_model=DataSourceSummary)
def get_source(name: str) -> DataSourceSummary:
    row = get_data_source(name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    return DataSourceSummary(**row)


@router.put("/{name}", response_model=DataSourceSummary)
def edit_source(name: str, req: SourceEditRequest) -> DataSourceSummary:
    existing = get_data_source(name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    row = upsert_data_source(
        name=name,
        display_name=req.display_name,
        kind=req.kind,
        vendor=req.vendor,
        auth_type=req.auth_type,
        base_url=req.base_url,
        protocol=req.protocol,
        capabilities=req.capabilities,
        rate_limits=req.rate_limits,
        credentials_ref=req.credentials_ref,
        enabled=req.enabled,
        meta=req.meta,
    )
    _persist_source_library(source=row, req=req, change_kind="edit")
    return DataSourceSummary(**row)


@router.patch("/{name}", response_model=DataSourceSummary)
def toggle_source(name: str, req: ToggleRequest) -> DataSourceSummary:
    row = set_data_source_enabled(name, req.enabled)
    if row is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    return DataSourceSummary(**row)


@router.get("/{name}/metadata-versions", response_model=list[SourceMetadataVersionView])
def source_metadata_versions(name: str) -> list[SourceMetadataVersionView]:
    with get_session() as session:
        rows = session.execute(
            select(SourceMetadataVersion)
            .where(SourceMetadataVersion.source_name == name)
            .order_by(SourceMetadataVersion.version.desc())
        ).scalars().all()
        return [_version_view(row) for row in rows]


@router.get("/{name}/probe", response_model=ProbeResponse)
def probe_source(name: str) -> ProbeResponse:
    meta = get_data_source(name)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    adapter = _load_adapter(name)
    if adapter is None:
        return ProbeResponse(
            name=name,
            ok=False,
            message="no runtime adapter registered for this source",
            details={"kind": meta["kind"]},
        )
    try:
        result = adapter.probe()
    except Exception as exc:  # pragma: no cover
        return ProbeResponse(name=name, ok=False, message=str(exc))
    return ProbeResponse(
        name=name,
        ok=bool(result.ok),
        message=result.message,
        details=dict(result.details or {}),
    )


# ---------------------------------------------------------------------------
# URL importer probe + setup wizard endpoints
# ---------------------------------------------------------------------------
class ImportProbeRequest(BaseModel):
    raw_source_url: str | None = None
    uri: str | None = None
    reference_path: str | None = None
    timeout_s: float = Field(default=5.0, ge=0.5, le=30.0)


class ImportProbeResponse(BaseModel):
    detected_kind: str
    detected_protocol: str
    suggested_default_node: str
    suggested_manifest: dict[str, Any] = Field(default_factory=dict)
    schema_hints: dict[str, Any] = Field(default_factory=dict)
    reachable: bool = False
    status_code: int | None = None
    message: str = ""


@router.post("/import/probe", response_model=ImportProbeResponse)
def probe_import(req: ImportProbeRequest) -> ImportProbeResponse:
    """Sniff a raw URL/URI/path before persisting via :func:`import_source`.

    Returns the detected ``kind`` / ``protocol``, the suggested manifest
    source node, and a best-effort reachability check.
    """
    candidate = (req.raw_source_url or req.uri or req.reference_path or "").strip()
    if not candidate:
        raise HTTPException(status_code=400, detail="provide raw_source_url, uri, or reference_path")
    default_node = _infer_default_node(req.raw_source_url or req.uri, req.reference_path)
    lower = candidate.lower()
    if lower.startswith(("http://", "https://")):
        kind = "rest_api"
        protocol = "https/json" if lower.startswith("https://") else "http/json"
    elif lower.startswith(("s3://", "minio://")):
        kind = "object_store"
        protocol = "s3"
    elif lower.startswith("gs://"):
        kind = "object_store"
        protocol = "gcs"
    elif lower.startswith(("az://", "abfs://", "azure://")):
        kind = "object_store"
        protocol = "azure_blob"
    elif req.reference_path:
        kind = "local_file"
        protocol = "file"
    else:
        kind = "rest_api"
        protocol = "https/json"

    reachable = False
    status_code: int | None = None
    message = ""
    if lower.startswith(("http://", "https://")):
        try:
            import httpx

            with httpx.Client(timeout=req.timeout_s, follow_redirects=True) as client:
                head = client.head(candidate)
                status_code = head.status_code
                reachable = head.status_code < 400
                message = (
                    f"HEAD {head.status_code}"
                    if reachable
                    else f"HEAD failed ({head.status_code})"
                )
        except Exception as exc:  # noqa: BLE001
            message = f"probe failed: {exc}"
    elif req.reference_path:
        path = Path(req.reference_path).expanduser()
        reachable = path.exists()
        message = "path exists" if reachable else "path not found"

    suggested_manifest = {
        "name": "import-preview",
        "namespace": "imports",
        "source": {
            "name": default_node,
            "kwargs": {
                "url": candidate if lower.startswith(("http://", "https://")) else None,
                "path": req.reference_path,
            },
        },
        "transforms": [],
        "sink": {
            "name": "sink.iceberg",
            "kwargs": {"namespace": "imports", "table": "preview"},
        },
    }

    schema_hints: dict[str, Any] = {}
    if lower.endswith((".csv", ".csv.gz")):
        schema_hints = {"format": "csv"}
    elif lower.endswith((".parquet", ".pq")):
        schema_hints = {"format": "parquet"}
    elif lower.endswith((".json", ".jsonl", ".ndjson")):
        schema_hints = {"format": "json"}
    elif lower.endswith((".zip", ".tar", ".tar.gz", ".tgz")):
        schema_hints = {"format": "archive"}

    return ImportProbeResponse(
        detected_kind=kind,
        detected_protocol=protocol,
        suggested_default_node=default_node,
        suggested_manifest=suggested_manifest,
        schema_hints=schema_hints,
        reachable=reachable,
        status_code=status_code,
        message=message,
    )


class SetupWizardStepView(BaseModel):
    id: str
    label: str
    prompt: str
    optional: bool = False
    fields: list[dict[str, Any]] = Field(default_factory=list)


class SetupWizardView(BaseModel):
    source_key: str
    display_name: str
    description: str
    documentation_url: str | None = None
    steps: list[SetupWizardStepView] = Field(default_factory=list)


class SetupWizardStepRequest(BaseModel):
    step_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SetupWizardStepResponse(BaseModel):
    ok: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    next_step: str | None = None


def _wizard_view(wizard: SourceSetupWizard) -> SetupWizardView:
    return SetupWizardView(
        source_key=wizard.source_key,
        display_name=wizard.display_name,
        description=wizard.description,
        documentation_url=wizard.documentation_url,
        steps=[SetupWizardStepView(**s.to_dict()) for s in wizard.steps],
    )


@router.get("/wizards", response_model=list[SetupWizardView])
def list_setup_wizards() -> list[SetupWizardView]:
    """List all curated source setup wizards."""
    return [_wizard_view(w) for w in list_wizards()]


@router.get("/{name}/setup-wizard", response_model=SetupWizardView)
def get_setup_wizard(name: str) -> SetupWizardView:
    wizard = get_wizard(name)
    if wizard is None:
        raise HTTPException(
            status_code=404,
            detail=f"no setup wizard registered for source {name!r}; supported: {sorted(WIZARDS)}",
        )
    return _wizard_view(wizard)


@router.post("/{name}/setup-wizard", response_model=SetupWizardStepResponse)
def run_setup_wizard_step(
    name: str, req: SetupWizardStepRequest
) -> SetupWizardStepResponse:
    wizard = get_wizard(name)
    if wizard is None:
        raise HTTPException(
            status_code=404,
            detail=f"no setup wizard registered for source {name!r}",
        )
    step = wizard.step(req.step_id)
    if step is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown step {req.step_id!r}; valid steps: {[s.id for s in wizard.steps]}",
        )
    result = wizard.run_step(req.step_id, req.payload)
    if result.next_step is None:
        # default: advance to the next step in declaration order
        ids = [s.id for s in wizard.steps]
        try:
            idx = ids.index(req.step_id)
            next_id = ids[idx + 1] if idx + 1 < len(ids) else None
        except ValueError:
            next_id = None
    else:
        next_id = result.next_step
    return SetupWizardStepResponse(
        ok=result.ok,
        message=result.message,
        details=result.details,
        next_step=next_id,
    )
