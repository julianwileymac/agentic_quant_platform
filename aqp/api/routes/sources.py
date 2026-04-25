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

from aqp.config import settings
from aqp.data.sources.base import ProbeResult
from aqp.data.sources.registry import (
    get_data_source,
    list_data_sources,
    set_data_source_enabled,
)

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


@router.get("", response_model=list[DataSourceSummary])
def list_sources(enabled_only: bool = False) -> list[DataSourceSummary]:
    return [DataSourceSummary(**row) for row in list_data_sources(enabled_only=enabled_only)]


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


@router.patch("/{name}", response_model=DataSourceSummary)
def toggle_source(name: str, req: ToggleRequest) -> DataSourceSummary:
    row = set_data_source_enabled(name, req.enabled)
    if row is None:
        raise HTTPException(status_code=404, detail=f"source {name!r} not found")
    return DataSourceSummary(**row)


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
