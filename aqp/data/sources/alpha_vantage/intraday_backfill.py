"""Resumable Alpha Vantage intraday OHLCV backfill and delta loader."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aqp.config import settings
from aqp.data import iceberg_catalog
from aqp.data.sources.alpha_vantage.client import AlphaVantageClient
from aqp.data.sources.alpha_vantage.coordination import (
    AlphaVantageIntradayCoordinationRequest,
    AlphaVantageRequestCoordinator,
    ProgressCallback,
)
from aqp.data.sources.alpha_vantage.datahub import emit_dataset_properties
from aqp.data.sources.alpha_vantage.intraday_plan import (
    IntradayDeltaState,
    IntradayRequestComponent,
    delta_state_path,
    load_delta_state,
    read_components,
    save_delta_state,
    update_component_status,
)

logger = logging.getLogger(__name__)


@dataclass
class IntradayComponentResult:
    component_id: str
    vt_symbol: str
    month: str
    status: str
    fetched_rows: int = 0
    duplicate_rows: int = 0
    rows_written: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntradayLoadResult:
    manifest_path: str
    iceberg_identifier: str
    started_at: str
    finished_at: str | None = None
    components_processed: int = 0
    rows_written: int = 0
    duplicate_rows: int = 0
    results: list[IntradayComponentResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_path": self.manifest_path,
            "iceberg_identifier": self.iceberg_identifier,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "components_processed": int(self.components_processed),
            "rows_written": int(self.rows_written),
            "duplicate_rows": int(self.duplicate_rows),
            "results": [entry.to_dict() for entry in self.results],
        }


class IntradayBackfillLoader:
    """Load planned monthly intraday components into the Alpha Vantage Iceberg table."""

    def __init__(
        self,
        client: AlphaVantageClient | None = None,
        *,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        self.client = client or AlphaVantageClient()
        self._owns_client = client is None
        self.progress_cb = progress_cb

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    @property
    def iceberg_identifier(self) -> str:
        return f"{settings.alpha_vantage_intraday_namespace}.{settings.alpha_vantage_intraday_table}"

    def run_manifest(
        self,
        manifest_path: str | Path,
        *,
        batch_size: int | None = None,
        statuses: set[str] | None = None,
        repair: bool = False,
        cache: bool = True,
        cache_ttl: float | None = None,
    ) -> IntradayLoadResult:
        health = iceberg_catalog.health_check()
        if not health.get("ok"):
            raise RuntimeError(
                "Iceberg catalog is not reachable: "
                f"{health.get('error')} (type={health.get('type')}, uri={health.get('uri')})"
            )
        record_run_start_or_raise(manifest_path)
        components = read_components(manifest_path)
        eligible_statuses = statuses or {"pending", "failed"}
        pending = [
            component
            for component in components
            if repair or component.status in eligible_statuses
        ]
        limit = int(batch_size or settings.alpha_vantage_intraday_batch_size or len(pending) or 0)
        selected = pending[:limit] if limit > 0 else pending
        result = IntradayLoadResult(
            manifest_path=str(Path(manifest_path).expanduser()),
            iceberg_identifier=self.iceberg_identifier,
            started_at=datetime.now(UTC).isoformat(),
        )
        for component in selected:
            entry = self.run_component(
                component,
                manifest_path=manifest_path,
                cache=cache,
                cache_ttl=cache_ttl,
            )
            result.results.append(entry)
            result.components_processed += 1
            result.rows_written += entry.rows_written
            result.duplicate_rows += entry.duplicate_rows
        result.finished_at = datetime.now(UTC).isoformat()
        self._update_delta_state(manifest_path, result)
        if result.rows_written:
            self.emit_datahub_metadata(result)
        return result

    def run_component(
        self,
        component: IntradayRequestComponent,
        *,
        manifest_path: str | Path,
        cache: bool = True,
        cache_ttl: float | None = None,
    ) -> IntradayComponentResult:
        coordinator = AlphaVantageRequestCoordinator(self.client, progress_cb=self.progress_cb)
        result = coordinator.run_intraday_component(
            AlphaVantageIntradayCoordinationRequest.from_component(
                component,
                iceberg_identifier=self.iceberg_identifier,
                cache=cache,
                cache_ttl=cache_ttl,
            )
        )
        if result.status == "completed":
            update_component_status(
                manifest_path,
                component.component_id,
                status="completed",
                status_reason="rows_appended",
                rows_written=result.rows_written,
                error=None,
            )
            return IntradayComponentResult(
                component_id=component.component_id,
                vt_symbol=component.vt_symbol,
                month=component.month,
                status="completed",
                fetched_rows=result.fetched_rows,
                duplicate_rows=result.duplicate_rows,
                rows_written=result.rows_written,
            )

        if result.status == "skipped":
            reason = result.error or "skipped"
            update_component_status(
                manifest_path,
                component.component_id,
                status="skipped",
                status_reason=reason,
                rows_written=0,
                error=None if reason in {"no_provider_rows", "no_new_rows_after_dedup"} else reason,
            )
            return IntradayComponentResult(
                component_id=component.component_id,
                vt_symbol=component.vt_symbol,
                month=component.month,
                status="skipped",
                error=reason,
                fetched_rows=result.fetched_rows,
                duplicate_rows=result.duplicate_rows,
            )

        update_component_status(
            manifest_path,
            component.component_id,
            status="failed",
            status_reason="exception",
            rows_written=0,
            error=result.error,
        )
        return IntradayComponentResult(
            component_id=component.component_id,
            vt_symbol=component.vt_symbol,
            month=component.month,
            status="failed",
            error=result.error,
        )

    def emit_datahub_metadata(self, result: IntradayLoadResult) -> bool:
        return emit_dataset_properties(
            platform="iceberg",
            name=self.iceberg_identifier,
            description="Alpha Vantage 1-minute intraday OHLCV data loaded by AQP",
            properties={
                "provider": "alpha_vantage",
                "function": "TIME_SERIES_INTRADAY",
                "interval": settings.alpha_vantage_intraday_interval,
                "iceberg_identifier": self.iceberg_identifier,
                "manifest_path": result.manifest_path,
                "rows_written": result.rows_written,
                "components_processed": result.components_processed,
                "finished_at": result.finished_at,
            },
        )

    def _update_delta_state(self, manifest_path: str | Path, result: IntradayLoadResult) -> None:
        if not result.rows_written:
            return
        manifest_dir = Path(manifest_path).expanduser().parent
        state_path = delta_state_path(settings.alpha_vantage_intraday_interval, manifest_dir)
        state = load_delta_state(state_path)
        symbols = sorted(
            {entry.vt_symbol for entry in result.results if entry.rows_written > 0}
        )
        if not symbols:
            return
        try:
            latest = iceberg_catalog.latest_timestamps_for_symbols(
                self.iceberg_identifier,
                symbols=symbols,
            )
        except Exception:
            logger.exception(
                "latest_timestamps_for_symbols failed; delta state unchanged for %d symbols",
                len(symbols),
            )
            return
        if not latest:
            return
        for vt_symbol, ts in latest.items():
            iso = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            state[str(vt_symbol)] = IntradayDeltaState(
                vt_symbol=str(vt_symbol),
                interval=settings.alpha_vantage_intraday_interval,
                latest_timestamp=iso,
            )
        save_delta_state(state_path, state)


def run_intraday_manifest(**kwargs: Any) -> IntradayLoadResult:
    manifest_path = kwargs.pop("manifest_path")
    progress_cb = kwargs.pop("progress_cb", None)
    loader = IntradayBackfillLoader(progress_cb=progress_cb)
    try:
        return loader.run_manifest(manifest_path, **kwargs)
    finally:
        loader.close()


__all__ = [
    "IntradayBackfillLoader",
    "IntradayComponentResult",
    "IntradayLoadResult",
    "run_intraday_manifest",
]


def record_run_start_or_raise(manifest_path: str | Path) -> Path:
    """Persist run starts and reject restart storms.

    The guard is intentionally file-based so it protects direct scripts, API
    tasks, and Dagster launches that share the same manifest directory.
    """

    max_starts = int(settings.alpha_vantage_intraday_run_guard_max_starts or 0)
    window_seconds = int(settings.alpha_vantage_intraday_run_guard_window_seconds or 0)
    if max_starts <= 0 or window_seconds <= 0:
        return _guard_path(manifest_path)

    path = _guard_path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    entries = _read_guard_entries(path)
    cutoff = now.timestamp() - window_seconds
    recent = [
        entry
        for entry in entries
        if float(entry.get("started_at_epoch", 0.0) or 0.0) >= cutoff
    ]
    if len(recent) >= max_starts:
        oldest = min(float(entry.get("started_at_epoch", now.timestamp())) for entry in recent)
        retry_after = max(1, int(window_seconds - (now.timestamp() - oldest)))
        raise RuntimeError(
            "AlphaVantage intraday run guard tripped: "
            f"{len(recent)} starts in {window_seconds}s (max={max_starts}). "
            f"Retry after approximately {retry_after}s."
        )

    recent.append(
        {
            "started_at": now.isoformat(),
            "started_at_epoch": now.timestamp(),
            "manifest_path": str(Path(manifest_path).expanduser()),
        }
    )
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(recent, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def _guard_path(manifest_path: str | Path) -> Path:
    return Path(manifest_path).expanduser().parent / "intraday_run_guard.json"


def _read_guard_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to read intraday run guard file %s", path, exc_info=True)
        return []
    if not isinstance(payload, list):
        return []
    return [dict(item) for item in payload if isinstance(item, dict)]
