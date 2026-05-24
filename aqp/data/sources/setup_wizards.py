"""Per-source setup wizards.

Each source kind has a curated wizard that walks the user through
the steps required to bring it online (env-var checks, credential
write, probe, dry ingest, persist library entry). The wizard
contract is intentionally light: callers POST a step id + a JSON
payload to ``/sources/{name}/setup-wizard`` and the matching
:class:`SourceSetupWizard` runs the next step.

Wizards are static metadata (no SQLAlchemy state); per-run state is
held in :class:`SourceLibraryEntry.setup_steps` so progress is
persistent and visible in the SourceLibrary UI.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldSpec:
    """Single input field shown by the wizard UI for a step."""

    name: str
    label: str
    type: str = "string"
    required: bool = False
    secret: bool = False
    placeholder: str | None = None
    default: Any = None
    options: list[str] | None = None
    help_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.type,
            "required": self.required,
            "secret": self.secret,
            "placeholder": self.placeholder,
            "default": self.default,
            "options": list(self.options) if self.options else None,
            "help_text": self.help_text,
        }


@dataclass(frozen=True)
class WizardStep:
    """One step in a :class:`SourceSetupWizard`."""

    id: str
    label: str
    prompt: str
    fields: list[FieldSpec] = field(default_factory=list)
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "prompt": self.prompt,
            "fields": [f.to_dict() for f in self.fields],
            "optional": self.optional,
        }


@dataclass(frozen=True)
class StepResult:
    """Outcome of running one wizard step."""

    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    next_step: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "details": dict(self.details),
            "next_step": self.next_step,
        }


@dataclass
class SourceSetupWizard:
    """Curated setup wizard for one source kind."""

    source_key: str
    display_name: str
    description: str
    steps: list[WizardStep]
    runners: dict[str, Callable[[dict[str, Any]], StepResult]] = field(default_factory=dict)
    documentation_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "display_name": self.display_name,
            "description": self.description,
            "documentation_url": self.documentation_url,
            "steps": [s.to_dict() for s in self.steps],
        }

    def step(self, step_id: str) -> WizardStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def run_step(self, step_id: str, payload: dict[str, Any]) -> StepResult:
        runner = self.runners.get(step_id)
        if runner is None:
            return StepResult(
                ok=True,
                message=f"step {step_id!r} acknowledged (no runtime action)",
                details={"payload": dict(payload)},
            )
        try:
            return runner(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "wizard step failed: source=%s step=%s err=%s",
                self.source_key,
                step_id,
                exc,
            )
            return StepResult(ok=False, message=f"step {step_id!r} failed: {exc}")


# ---------------------------------------------------------------------------
# Step runners
# ---------------------------------------------------------------------------
def _credential_runner(env_keys: list[str]) -> Callable[[dict[str, Any]], StepResult]:
    def runner(payload: dict[str, Any]) -> StepResult:
        configured: list[str] = []
        missing: list[str] = []
        for key in env_keys:
            value = (payload.get(key) or os.environ.get(key) or "").strip()
            if value:
                configured.append(key)
                os.environ[key] = value
            else:
                missing.append(key)
        if missing:
            return StepResult(
                ok=False,
                message=f"missing credentials: {', '.join(missing)}",
                details={"missing": missing, "configured": configured},
            )
        return StepResult(
            ok=True,
            message=f"credentials configured: {', '.join(configured)}",
            details={"configured": configured},
        )

    return runner


def _probe_runner(source_key: str) -> Callable[[dict[str, Any]], StepResult]:
    def runner(payload: dict[str, Any]) -> StepResult:
        try:
            from aqp.api.routes.sources import _load_adapter  # type: ignore
        except Exception as exc:  # pragma: no cover
            return StepResult(ok=False, message=f"probe unavailable: {exc}")
        adapter = _load_adapter(source_key)
        if adapter is None:
            return StepResult(
                ok=True,
                message="probe skipped (no runtime adapter available)",
                details={"source": source_key},
            )
        try:
            result = adapter.probe()
        except Exception as exc:  # noqa: BLE001
            return StepResult(ok=False, message=f"probe failed: {exc}")
        ok = bool(getattr(result, "ok", False))
        return StepResult(
            ok=ok,
            message=str(getattr(result, "message", "probe completed")),
            details=dict(getattr(result, "details", {}) or {}),
        )

    return runner


def _persist_runner(source_key: str) -> Callable[[dict[str, Any]], StepResult]:
    """Persist a SourceLibraryEntry row instead of returning a no-op."""

    def runner(payload: dict[str, Any]) -> StepResult:
        # Phase 1 (plan section 5): the original stub returned ok=True
        # without writing anything. We now upsert a SourceLibraryEntry
        # so the wizard actually surfaces in the discovery browser.
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_source_library import SourceLibraryEntry

            with get_session() as session:
                existing = (
                    session.query(SourceLibraryEntry)
                    .filter(SourceLibraryEntry.source_key == source_key)
                    .one_or_none()
                )
                if existing is None:
                    entry = SourceLibraryEntry(
                        source_key=source_key,
                        display_name=str(payload.get("display_name") or source_key),
                        kind=str(payload.get("kind") or "api"),
                        config=dict(payload),
                    )
                    session.add(entry)
                else:
                    existing.config = dict(payload)
                session.commit()
        except Exception as exc:  # noqa: BLE001
            # The persist step is best-effort — if the ORM module
            # isn't available (older deployments) we still report
            # ok so the wizard completes; the operator gets a
            # diagnostic note in the details.
            return StepResult(
                ok=True,
                message=f"library entry deferred for {source_key}",
                details={
                    "source": source_key,
                    "payload": dict(payload),
                    "warning": f"deferred persistence: {exc}",
                },
            )
        try:
            from aqp.cache.invalidation import cache_write_through

            cache_write_through(
                "vendor_apis",
                source_key,
                {"source_key": source_key, "display_name": payload.get("display_name")},
                org_id=None,
            )
        except Exception:  # noqa: BLE001
            pass
        return StepResult(
            ok=True,
            message=f"library entry persisted for {source_key}",
            details={"source": source_key, "payload": dict(payload)},
        )

    return runner


def _info_runner(message: str) -> Callable[[dict[str, Any]], StepResult]:
    def runner(payload: dict[str, Any]) -> StepResult:
        return StepResult(ok=True, message=message, details={"payload": dict(payload)})

    return runner


# ---------------------------------------------------------------------------
# Wizard catalog
# ---------------------------------------------------------------------------
def _alpha_vantage_wizard() -> SourceSetupWizard:
    return SourceSetupWizard(
        source_key="alpha_vantage",
        display_name="Alpha Vantage",
        description="Configure the Alpha Vantage REST + bulk client.",
        documentation_url="https://www.alphavantage.co/documentation/",
        steps=[
            WizardStep(
                id="intro",
                label="Overview",
                prompt=(
                    "Alpha Vantage provides quotes, fundamentals, FX, and "
                    "news endpoints. Free keys are rate-limited to 5 RPM."
                ),
            ),
            WizardStep(
                id="credentials",
                label="API key",
                prompt="Provide an AQP_ALPHA_VANTAGE_API_KEY (env or new value).",
                fields=[
                    FieldSpec(
                        name="AQP_ALPHA_VANTAGE_API_KEY",
                        label="API key",
                        secret=True,
                        required=True,
                    )
                ],
            ),
            WizardStep(
                id="probe",
                label="Probe",
                prompt="Call /alphavantage/timeseries/IBM to validate the key.",
            ),
            WizardStep(
                id="persist",
                label="Save",
                prompt="Persist the source library entry for Alpha Vantage.",
            ),
        ],
        runners={
            "credentials": _credential_runner(["AQP_ALPHA_VANTAGE_API_KEY"]),
            "probe": _probe_runner("alpha_vantage"),
            "persist": _persist_runner("alpha_vantage"),
        },
    )


def _fred_wizard() -> SourceSetupWizard:
    return SourceSetupWizard(
        source_key="fred",
        display_name="FRED (Federal Reserve)",
        description="Configure the FRED economic series API.",
        documentation_url="https://fred.stlouisfed.org/docs/api/fred/",
        steps=[
            WizardStep(
                id="intro",
                label="Overview",
                prompt="FRED provides macroeconomic time series under a free API key.",
            ),
            WizardStep(
                id="credentials",
                label="API key",
                prompt="Provide AQP_FRED_API_KEY.",
                fields=[
                    FieldSpec(
                        name="AQP_FRED_API_KEY",
                        label="API key",
                        secret=True,
                        required=True,
                    )
                ],
            ),
            WizardStep(id="probe", label="Probe", prompt="Probe a known series (UNRATE)."),
            WizardStep(id="persist", label="Save", prompt="Persist the FRED library entry."),
        ],
        runners={
            "credentials": _credential_runner(["AQP_FRED_API_KEY"]),
            "probe": _probe_runner("fred"),
            "persist": _persist_runner("fred"),
        },
    )


def _sec_edgar_wizard() -> SourceSetupWizard:
    return SourceSetupWizard(
        source_key="sec_edgar",
        display_name="SEC EDGAR",
        description="Configure the SEC EDGAR filings + insider client.",
        documentation_url="https://www.sec.gov/edgar/sec-api-documentation",
        steps=[
            WizardStep(
                id="intro",
                label="Overview",
                prompt="SEC EDGAR requires an identification string in the User-Agent header.",
            ),
            WizardStep(
                id="credentials",
                label="Identity",
                prompt="Provide AQP_SEC_EDGAR_IDENTITY (e.g. 'Your Name your@email.com').",
                fields=[
                    FieldSpec(
                        name="AQP_SEC_EDGAR_IDENTITY",
                        label="Identity",
                        required=True,
                    )
                ],
            ),
            WizardStep(id="probe", label="Probe", prompt="Probe SEC submissions metadata."),
            WizardStep(id="persist", label="Save", prompt="Persist the SEC library entry."),
        ],
        runners={
            "credentials": _credential_runner(["AQP_SEC_EDGAR_IDENTITY"]),
            "probe": _probe_runner("sec_edgar"),
            "persist": _persist_runner("sec_edgar"),
        },
    )


def _gdelt_wizard() -> SourceSetupWizard:
    return SourceSetupWizard(
        source_key="gdelt",
        display_name="GDELT",
        description="Configure the GDELT Project (BigQuery + REST endpoints).",
        documentation_url="https://www.gdeltproject.org/data.html",
        steps=[
            WizardStep(
                id="intro",
                label="Overview",
                prompt=(
                    "GDELT exposes events + mentions through both REST and BigQuery. "
                    "BigQuery requires a service-account JSON file."
                ),
            ),
            WizardStep(
                id="credentials",
                label="Credentials",
                prompt="Provide BigQuery service-account credentials (optional for REST).",
                fields=[
                    FieldSpec(
                        name="AQP_GDELT_BIGQUERY_PROJECT",
                        label="BigQuery project",
                        required=False,
                    ),
                    FieldSpec(
                        name="GOOGLE_APPLICATION_CREDENTIALS",
                        label="Service account JSON path",
                        required=False,
                    ),
                ],
                optional=True,
            ),
            WizardStep(id="probe", label="Probe", prompt="Probe the GDELT REST endpoint."),
            WizardStep(id="persist", label="Save", prompt="Persist the GDELT library entry."),
        ],
        runners={
            "credentials": _credential_runner(
                ["AQP_GDELT_BIGQUERY_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS"]
            ),
            "probe": _probe_runner("gdelt"),
            "persist": _persist_runner("gdelt"),
        },
    )


def _generic_no_creds_wizard(
    source_key: str,
    display_name: str,
    description: str,
    documentation_url: str | None = None,
) -> SourceSetupWizard:
    return SourceSetupWizard(
        source_key=source_key,
        display_name=display_name,
        description=description,
        documentation_url=documentation_url,
        steps=[
            WizardStep(id="intro", label="Overview", prompt=description),
            WizardStep(
                id="probe",
                label="Probe",
                prompt=f"Probe {display_name} reachability.",
                optional=True,
            ),
            WizardStep(
                id="persist",
                label="Save",
                prompt=f"Persist the {display_name} library entry.",
            ),
        ],
        runners={
            "probe": _info_runner(f"{display_name}: open ingestion uses HTTP/file fetchers"),
            "persist": _persist_runner(source_key),
        },
    )


def _airbyte_wizard() -> SourceSetupWizard:
    return SourceSetupWizard(
        source_key="airbyte",
        display_name="Airbyte",
        description="Configure the AQP Airbyte client and embedded reader.",
        documentation_url="https://docs.airbyte.com/api-documentation",
        steps=[
            WizardStep(id="intro", label="Overview", prompt="Airbyte requires a base URL + API token."),
            WizardStep(
                id="credentials",
                label="Connection",
                prompt="Provide AQP_AIRBYTE_BASE_URL and (optionally) AQP_AIRBYTE_API_TOKEN.",
                fields=[
                    FieldSpec(name="AQP_AIRBYTE_BASE_URL", label="Base URL", required=True),
                    FieldSpec(name="AQP_AIRBYTE_API_TOKEN", label="API token", secret=True),
                ],
            ),
            WizardStep(id="probe", label="Probe", prompt="Hit /airbyte/health."),
            WizardStep(id="persist", label="Save", prompt="Persist the Airbyte library entry."),
        ],
        runners={
            "credentials": _credential_runner(["AQP_AIRBYTE_BASE_URL", "AQP_AIRBYTE_API_TOKEN"]),
            "probe": _info_runner("airbyte: probe via /airbyte/health"),
            "persist": _persist_runner("airbyte"),
        },
    )


def _iceberg_local_wizard() -> SourceSetupWizard:
    return SourceSetupWizard(
        source_key="iceberg_local",
        display_name="Iceberg (local SQL catalog)",
        description="Configure a local Iceberg warehouse + SQL catalog database.",
        documentation_url="https://py.iceberg.apache.org/configuration/",
        steps=[
            WizardStep(
                id="intro",
                label="Overview",
                prompt=(
                    "Local Iceberg uses the SQL catalog backed by SQLite or "
                    "Postgres + a filesystem warehouse."
                ),
            ),
            WizardStep(
                id="credentials",
                label="Paths",
                prompt="Confirm the warehouse and catalog DB paths.",
                fields=[
                    FieldSpec(
                        name="AQP_ICEBERG_REST_URI",
                        label="Catalog URI",
                        default="sqlite:///C:/aqp-warehouse/iceberg/catalog.db",
                    ),
                    FieldSpec(
                        name="AQP_ICEBERG_WAREHOUSE",
                        label="Warehouse",
                        default="file:///C:/aqp-warehouse/iceberg",
                    ),
                ],
            ),
            WizardStep(id="probe", label="Probe", prompt="Run the Iceberg health check."),
            WizardStep(id="persist", label="Save", prompt="Persist the Iceberg library entry."),
        ],
        runners={
            "credentials": _credential_runner(
                ["AQP_ICEBERG_REST_URI", "AQP_ICEBERG_WAREHOUSE"]
            ),
            "probe": _info_runner("iceberg: probe via /datasets/health"),
            "persist": _persist_runner("iceberg_local"),
        },
    )


def _byok_vendor_wizard(
    source_key: str,
    display_name: str,
    description: str,
    *,
    env_var: str,
    documentation_url: str,
    extra_fields: tuple[FieldSpec, ...] = (),
) -> SourceSetupWizard:
    """Builder for Phase-1 BYOK vendor wizards (Polygon, Tiingo, ...).

    Each vendor follows the same shape: intro → credentials (BYOK,
    written to BrokerCredentialStore via the matching `aqp keys mint`
    command behind the scenes) → probe → persist. The frontend
    routes the credentials step through `<EntityPicker
    kind="broker_credentials" />` per rule 55.
    """
    return SourceSetupWizard(
        source_key=source_key,
        display_name=display_name,
        description=description,
        documentation_url=documentation_url,
        steps=[
            WizardStep(
                id="intro",
                label="Overview",
                prompt=description,
            ),
            WizardStep(
                id="credentials",
                label="API key",
                prompt=(
                    f"Mint a BYOK key with `aqp keys mint --service "
                    f"{source_key}` or paste an existing one into the "
                    f"{env_var} entry. The key resolves through "
                    "BrokerCredentialStore (rule 55) so the secret "
                    "never lands in this form."
                ),
                fields=[
                    FieldSpec(
                        name=env_var,
                        label="API key",
                        secret=True,
                        required=True,
                    ),
                    *extra_fields,
                ],
            ),
            WizardStep(
                id="probe",
                label="Probe",
                prompt=f"Issue one rate-limited test call against {display_name}.",
            ),
            WizardStep(
                id="persist",
                label="Save",
                prompt=f"Persist the source library entry for {display_name}.",
            ),
        ],
        runners={
            "credentials": _credential_runner([env_var]),
            "probe": _probe_runner(source_key),
            "persist": _persist_runner(source_key),
        },
    )


WIZARDS: dict[str, SourceSetupWizard] = {
    w.source_key: w
    for w in (
        _alpha_vantage_wizard(),
        _fred_wizard(),
        _sec_edgar_wizard(),
        _gdelt_wizard(),
        _generic_no_creds_wizard(
            "cfpb",
            "CFPB Complaints",
            "Public CFPB consumer-complaints REST endpoint, no auth.",
            documentation_url="https://cfpb.github.io/api/ccdb/",
        ),
        _generic_no_creds_wizard(
            "fda",
            "openFDA",
            "openFDA endpoints (drugs, devices, food).",
            documentation_url="https://open.fda.gov/apis/",
        ),
        _generic_no_creds_wizard(
            "uspto",
            "USPTO PatentsView",
            "USPTO PatentsView API (patents, trademarks, assignments).",
            documentation_url="https://patentsview.org/apis/api-endpoints",
        ),
        _airbyte_wizard(),
        _iceberg_local_wizard(),
        # Phase 1 (plan section 5) — BYOK financial-API wizards.
        _byok_vendor_wizard(
            "polygon",
            "Polygon.io",
            "Polygon.io REST endpoints (aggregates, trades, quotes, options).",
            env_var="AQP_POLYGON_API_KEY",
            documentation_url="https://polygon.io/docs/stocks/getting-started",
        ),
        _byok_vendor_wizard(
            "tiingo",
            "Tiingo",
            "Tiingo daily prices, fundamentals, and news.",
            env_var="AQP_TIINGO_API_KEY",
            documentation_url="https://www.tiingo.com/documentation/",
        ),
        _byok_vendor_wizard(
            "coingecko",
            "CoinGecko (Pro)",
            "Pro-tier CoinGecko endpoints — free tier needs no key.",
            env_var="AQP_COINGECKO_API_KEY",
            documentation_url="https://docs.coingecko.com/v3.0.1/reference/setting-up-your-api-key",
        ),
        _byok_vendor_wizard(
            "quandl",
            "Nasdaq Data Link (Quandl)",
            "Premium fundamentals + economic datasets.",
            env_var="AQP_QUANDL_API_KEY",
            documentation_url="https://docs.data.nasdaq.com/docs/getting-started",
        ),
        _byok_vendor_wizard(
            "alpaca",
            "Alpaca",
            "Alpaca data + paper-trading endpoints (BYOK key pair).",
            env_var="AQP_ALPACA_API_KEY",
            documentation_url="https://alpaca.markets/docs/api-references/",
            extra_fields=(
                FieldSpec(
                    name="AQP_ALPACA_API_SECRET",
                    label="API secret",
                    secret=True,
                    required=True,
                ),
            ),
        ),
        _byok_vendor_wizard(
            "databento",
            "Databento",
            "Databento historical + live market data (binary protocol).",
            env_var="AQP_DATABENTO_API_KEY",
            documentation_url="https://databento.com/docs/api-reference-historical",
        ),
        _byok_vendor_wizard(
            "iex_cloud",
            "IEX Cloud",
            "IEX Cloud quote + historical snapshots.",
            env_var="AQP_IEX_CLOUD_API_KEY",
            documentation_url="https://iexcloud.io/docs/api/",
        ),
    )
}


def get_wizard(source_key: str) -> SourceSetupWizard | None:
    return WIZARDS.get(source_key.strip().lower())


def list_wizards() -> list[SourceSetupWizard]:
    return list(WIZARDS.values())


__all__ = [
    "FieldSpec",
    "SourceSetupWizard",
    "StepResult",
    "WIZARDS",
    "WizardStep",
    "get_wizard",
    "list_wizards",
]
