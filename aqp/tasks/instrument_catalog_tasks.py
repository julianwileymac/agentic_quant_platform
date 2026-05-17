from __future__ import annotations

import logging
import math
import traceback
import uuid
from datetime import datetime
from typing import Any

from celery import shared_task
from sqlalchemy.dialects.postgresql import insert as pg_insert

from aqp.data.catalog.lineage import record_lineage
from aqp.data.fabric.identity import FabricHashMixin
from aqp.persistence.db import get_session
from aqp.persistence.models_instrument_catalog import InstrumentCatalog
from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


_ASSET_CLASS_MAP = {
    "Equities": "equity",
    "ETFs": "etf",
    "Funds": "fund",
    "Indices": "index",
    "Cryptos": "cryptocurrency",
    "Currencies": "currency",
    "Moneymarkets": "money_market",
}

_VOLATILE_HASH_FIELDS = frozenset(
    {"id", "content_hash", "created_at", "updated_at", "last_catalog_sync"}
)


def _scrub_nan(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _scrub_nan(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_scrub_nan(item) for item in value]
    try:
        if math.isnan(value) or math.isinf(value):  # type: ignore[arg-type]
            return None
    except Exception:  # noqa: BLE001
        pass
    return value


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
        try:
            maybe = value.to_dict()
            if isinstance(maybe, dict):
                return dict(maybe)
        except Exception:  # noqa: BLE001
            return {}
    try:
        return dict(value)
    except Exception:  # noqa: BLE001
        return {}


def _extract_ticker(index_value: Any, row: dict[str, Any]) -> str:
    for key in (
        "universal_ticker",
        "ticker",
        "symbol",
        "Ticker",
        "Symbol",
        "code",
        "Code",
    ):
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    text = str(index_value).strip()
    return text


def _extract_exchange(row: dict[str, Any]) -> str:
    for key in ("exchange_code", "exchange", "Exchange", "market", "Market"):
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "nan", "nat"}:
            return text
    return ""


def _row_dict_for_hash(row: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical row dict used for content-hash computation."""
    payload = dict(row)
    for key in _VOLATILE_HASH_FIELDS:
        payload.pop(key, None)
    return payload


def _flush_catalog_rows(session: Any, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    values = [dict(row) for row in rows]
    now = datetime.utcnow()
    dialect_name = getattr(getattr(session, "bind", None), "dialect", None)
    dialect_name = getattr(dialect_name, "name", "")
    if dialect_name == "postgresql":
        insert_stmt = pg_insert(InstrumentCatalog).values(values)
    else:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        insert_stmt = sqlite_insert(InstrumentCatalog).values(values)

    excluded = insert_stmt.excluded
    update_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["universal_ticker", "exchange_code"],
        set_={
            "metadata_blob": excluded.metadata_blob,
            "asset_class": excluded.asset_class,
            "content_hash": excluded.content_hash,
            "is_actively_traded": excluded.is_actively_traded,
            "schema_version": excluded.schema_version,
            "last_catalog_sync": excluded.last_catalog_sync,
            "updated_at": now,
        },
        where=InstrumentCatalog.content_hash.is_distinct_from(excluded.content_hash),
    )
    result = session.execute(update_stmt)
    return int(result.rowcount or 0)


@shared_task(
    name="aqp.tasks.sync_finance_database",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def sync_finance_database(self, *, batch_size: int = 1000) -> dict[str, int]:
    """Sync FinanceDatabase ontology into ``instrument_catalogs``."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", "Syncing FinanceDatabase into instrument catalog")
    scanned_total = 0
    upserted_total = 0
    errors_total = 0

    try:
        try:
            import financedatabase as fd
        except ImportError as exc:
            raise RuntimeError(
                "financedatabase is not installed. Install with `pip install financedatabase`."
            ) from exc

        batch_size = max(1, int(batch_size))
        with get_session() as session:
            for class_name, asset_class in _ASSET_CLASS_MAP.items():
                scanned_class = 0
                upserted_class = 0
                errors_class = 0
                buffer: list[dict[str, Any]] = []

                asset_cls = getattr(fd, class_name, None)
                if asset_cls is None:
                    logger.warning("FinanceDatabase class %s not found", class_name)
                    errors_class += 1
                    errors_total += 1
                    emit(
                        task_id,
                        "asset-class-progress",
                        f"{class_name}: class missing",
                        asset_class=class_name,
                        scanned=scanned_class,
                        upserted=upserted_class,
                        skipped=0,
                        errors=errors_class,
                    )
                    continue

                try:
                    frame = asset_cls().select()
                except Exception:  # noqa: BLE001
                    logger.exception("FinanceDatabase %s select() failed", class_name)
                    errors_class += 1
                    errors_total += 1
                    emit(
                        task_id,
                        "asset-class-progress",
                        f"{class_name}: select failed",
                        asset_class=class_name,
                        scanned=scanned_class,
                        upserted=upserted_class,
                        skipped=0,
                        errors=errors_class,
                    )
                    continue

                if frame is None or getattr(frame, "empty", False):
                    emit(
                        task_id,
                        "asset-class-progress",
                        f"{class_name}: no rows",
                        asset_class=class_name,
                        scanned=scanned_class,
                        upserted=upserted_class,
                        skipped=0,
                        errors=errors_class,
                    )
                    continue

                iterator = (
                    frame.iterrows()
                    if hasattr(frame, "iterrows") and callable(getattr(frame, "iterrows"))
                    else []
                )

                for index_value, row in iterator:
                    scanned_total += 1
                    scanned_class += 1
                    row_payload = _as_mapping(row)
                    universal_ticker = _extract_ticker(index_value, row_payload)
                    if not universal_ticker:
                        errors_total += 1
                        errors_class += 1
                        continue

                    clean_row = _scrub_nan(row_payload)
                    now = datetime.utcnow()
                    payload: dict[str, Any] = {
                        "universal_ticker": universal_ticker,
                        "asset_class": asset_class,
                        "exchange_code": _extract_exchange(row_payload),
                        "metadata_blob": clean_row,
                        "is_actively_traded": True,
                        "schema_version": 1,
                        "last_catalog_sync": now,
                    }
                    payload["content_hash"] = FabricHashMixin.compute_dict_hash(
                        _row_dict_for_hash(payload)
                    )
                    buffer.append(payload)

                    if len(buffer) >= batch_size:
                        upserted = _flush_catalog_rows(session, buffer)
                        upserted_total += upserted
                        upserted_class += upserted
                        buffer.clear()

                if buffer:
                    upserted = _flush_catalog_rows(session, buffer)
                    upserted_total += upserted
                    upserted_class += upserted
                    buffer.clear()

                skipped_class = max(0, scanned_class - upserted_class - errors_class)
                emit(
                    task_id,
                    "asset-class-progress",
                    f"{class_name}: scanned={scanned_class} upserted={upserted_class}",
                    asset_class=class_name,
                    scanned=scanned_class,
                    upserted=upserted_class,
                    skipped=skipped_class,
                    errors=errors_class,
                )

        skipped_total = max(0, scanned_total - upserted_total - errors_total)
        record_lineage(
            transform_kind="ingest.finance_database",
            summary=(
                f"Synced {upserted_total} rows across "
                f"{len(_ASSET_CLASS_MAP)} asset classes"
            ),
            target=None,
            actor="celery",
            actor_kind="service",
            service_name="aqp-data-fabric",
            rows_written=upserted_total,
            details={
                "asset_classes": list(_ASSET_CLASS_MAP.keys()),
                "scanned": scanned_total,
                "upserted": upserted_total,
                "skipped": skipped_total,
                "errors": errors_total,
            },
        )
        result = {
            "asset_classes_synced": len(_ASSET_CLASS_MAP),
            "upserted": upserted_total,
            "skipped": skipped_total,
            "errors": errors_total,
        }
        emit_done(task_id, result=result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "sync_finance_database failed\n%s",
            traceback.format_exc(),
        )
        emit_error(task_id, str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=self.default_retry_delay)
        raise


__all__ = [
    "sync_finance_database",
]
