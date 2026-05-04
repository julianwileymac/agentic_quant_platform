"""Data catalog and lineage persistence helpers."""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import func, select, text

from aqp.core.types import Symbol
from aqp.data.entities.sync import sync_dataset_version_entities
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    DataLink,
    DatasetCatalog,
    DatasetVersion,
    DataSource,
    Instrument,
)

logger = logging.getLogger(__name__)


def _advisory_xact_lock(session: Any, key: str) -> None:
    """Serialize catalog writes for one logical dataset on PostgreSQL."""
    try:
        dialect = session.get_bind().dialect.name
    except Exception:
        return
    if dialect != "postgresql":
        return
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": key})


def _resolve_code_version_sha() -> str | None:
    """Best-effort capture of the current git SHA at materialization time."""
    import os
    import subprocess

    if env := os.environ.get("AQP_CODE_VERSION_SHA"):
        return env.strip() or None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None
    return None


def register_dataset_version(
    *,
    name: str,
    provider: str,
    domain: str = "market.bars",
    df: pd.DataFrame | None = None,
    storage_uri: str | None = None,
    frequency: str | None = None,
    as_of: datetime | None = None,
    dataset_hash_value: str | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    file_count: int | None = None,
    iceberg_identifier: str | None = None,
    load_mode: str | None = None,
    source_uri: str | None = None,
    llm_annotations: dict[str, Any] | None = None,
    column_docs: list[dict[str, Any]] | None = None,
    engine_meta: dict[str, Any] | None = None,
    summary_row_count: int | None = None,
    summary_symbol_count: int | None = None,
) -> dict[str, Any]:
    """Persist a dataset catalog/version row and return lineage ids.

    The helper is intentionally best-effort: if the DB is unavailable, we log
    and return an empty mapping so ingestion still succeeds.

    For non-OHLCV (``domain != "market.bars"``) datasets the ``vt_symbol``
    / ``timestamp`` extraction and instrument upsert paths are skipped so
    generic Iceberg tables don't blow up on missing columns.

    ``engine_meta`` is the new (data-fabric expansion) bag of fields written
    to both ``dataset_catalogs`` and ``dataset_versions``: ``compute_backend``,
    ``dagster_asset_key``, ``datahub_urn``, ``code_version_sha``,
    ``materialization_engine``, ``dagster_run_id``, ``partition_key``,
    ``manifest_id``, ``pipeline_kind``, ``rows_written``,
    ``entity_extraction_status``.
    """
    engine_meta = dict(engine_meta or {})
    summary_mode = summary_row_count is not None
    has_engine_only = bool(iceberg_identifier and engine_meta)
    # Even with no rows we still want to surface the engine_meta on the
    # catalog so the UI shows the engine that ran (with zero rows).
    if (df is None or df.empty) and not summary_mode and not has_engine_only:
        return {}

    is_market_bars = (domain or "").startswith("market.bars")
    code_version_sha = engine_meta.pop("code_version_sha", None) or _resolve_code_version_sha()
    compute_backend = engine_meta.pop("compute_backend", None)
    dagster_asset_key = engine_meta.pop("dagster_asset_key", None)
    datahub_urn = engine_meta.pop("datahub_urn", None)
    materialization_engine = engine_meta.pop("materialization_engine", None) or compute_backend
    dagster_run_id = engine_meta.pop("dagster_run_id", None)
    partition_key = engine_meta.pop("partition_key", None)
    manifest_id_val = engine_meta.pop("manifest_id", None)
    pipeline_kind = engine_meta.pop("pipeline_kind", None)
    entity_extraction_status = engine_meta.pop("entity_extraction_status", None)
    rows_written_hint = engine_meta.pop("rows_written", None)

    try:
        if df is not None and not df.empty:
            if is_market_bars:
                ts = pd.to_datetime(df.get("timestamp"), errors="coerce")
                start_time = _to_dt(ts.min())
                end_time = _to_dt(ts.max())
                vt_symbols = sorted(
                    df.get("vt_symbol", pd.Series(dtype=str))
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                )
            else:
                start_time = end_time = None
                vt_symbols = []
            schema = _schema_snapshot(df)
            digest = dataset_hash_value or _dataset_hash(df)
        else:
            start_time = end_time = None
            vt_symbols = []
            schema = {"columns": [], "dtypes": {}}
            digest = dataset_hash_value
            if digest is None and summary_mode:
                digest = hashlib.sha256(
                    json.dumps(
                        {
                            "name": name,
                            "provider": provider,
                            "summary_row_count": summary_row_count,
                            "summary_symbol_count": summary_symbol_count,
                            "meta": meta or {},
                        },
                        sort_keys=True,
                        default=str,
                    ).encode()
                ).hexdigest()

        with get_session() as session:
            _advisory_xact_lock(session, f"dataset_catalog:{provider}:{name}")
            catalog = session.execute(
                select(DatasetCatalog)
                .where(DatasetCatalog.name == name)
                .where(DatasetCatalog.provider == provider)
                .limit(1)
            ).scalar_one_or_none()

            if catalog is None:
                catalog = DatasetCatalog(
                    name=name,
                    provider=provider,
                    domain=domain,
                    frequency=frequency,
                    storage_uri=storage_uri,
                    schema_json=schema,
                    tags=list(tags or []),
                    meta=dict(meta or {}),
                    iceberg_identifier=iceberg_identifier,
                    load_mode=load_mode or "managed",
                    source_uri=source_uri,
                    llm_annotations=dict(llm_annotations or {}),
                    column_docs=list(column_docs or []),
                    compute_backend=compute_backend,
                    dagster_asset_key=dagster_asset_key,
                    datahub_urn=datahub_urn,
                    entity_extraction_status=entity_extraction_status or "pending",
                    manifest_id=manifest_id_val,
                    pipeline_kind=pipeline_kind,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(catalog)
                session.flush()
            else:
                catalog.domain = domain or catalog.domain
                catalog.frequency = frequency or catalog.frequency
                catalog.storage_uri = storage_uri or catalog.storage_uri
                catalog.schema_json = schema or catalog.schema_json
                catalog.tags = list(tags or catalog.tags or [])
                catalog.meta = {**(catalog.meta or {}), **(meta or {})}
                if iceberg_identifier:
                    catalog.iceberg_identifier = iceberg_identifier
                if load_mode:
                    catalog.load_mode = load_mode
                if source_uri:
                    catalog.source_uri = source_uri
                if llm_annotations:
                    catalog.llm_annotations = {
                        **(catalog.llm_annotations or {}),
                        **(llm_annotations or {}),
                    }
                if column_docs:
                    catalog.column_docs = list(column_docs)
                if compute_backend:
                    catalog.compute_backend = compute_backend
                if dagster_asset_key:
                    catalog.dagster_asset_key = dagster_asset_key
                if datahub_urn:
                    catalog.datahub_urn = datahub_urn
                if entity_extraction_status:
                    catalog.entity_extraction_status = entity_extraction_status
                if manifest_id_val:
                    catalog.manifest_id = manifest_id_val
                if pipeline_kind:
                    catalog.pipeline_kind = pipeline_kind
                catalog.updated_at = datetime.utcnow()
                session.add(catalog)

            current_version = (
                session.execute(
                    select(func.max(DatasetVersion.version)).where(DatasetVersion.catalog_id == catalog.id)
                ).scalar_one()
                or 0
            )
            if summary_mode:
                row_count_val = int(summary_row_count or 0)
            elif rows_written_hint:
                row_count_val = int(rows_written_hint)
            elif df is not None:
                row_count_val = int(len(df))
            else:
                row_count_val = 0
            symbol_count_val = (
                int(summary_symbol_count)
                if summary_mode and summary_symbol_count is not None
                else int(len(vt_symbols))
            )
            columns_val = list(df.columns) if df is not None and not df.empty else (
                list((schema or {}).get("columns") or [])
            )
            row = DatasetVersion(
                catalog_id=catalog.id,
                version=int(current_version) + 1,
                status="active",
                as_of=as_of or datetime.utcnow(),
                start_time=start_time,
                end_time=end_time,
                row_count=row_count_val,
                symbol_count=symbol_count_val,
                file_count=int(file_count or symbol_count_val or 1),
                dataset_hash=digest,
                materialization_uri=storage_uri,
                columns=columns_val,
                schema_json=schema,
                meta=dict(meta or {}),
                materialization_engine=materialization_engine,
                dagster_run_id=dagster_run_id,
                partition_key=partition_key,
                code_version_sha=code_version_sha,
                created_at=datetime.utcnow(),
            )
            session.add(row)
            if is_market_bars:
                _upsert_instruments(session, vt_symbols)
            session.flush()
            if is_market_bars and vt_symbols:
                sync_result = sync_dataset_version_entities(
                    session=session,
                    catalog=catalog,
                    version=row,
                    vt_symbols=vt_symbols,
                    coverage_start=start_time,
                    coverage_end=end_time,
                )
                row.meta = {**(row.meta or {}), "entity_graph_sync": sync_result}
                catalog.meta = {**(catalog.meta or {}), "entity_graph_sync": sync_result}
                session.add(row)
                session.add(catalog)
            return {
                "dataset_catalog_id": catalog.id,
                "dataset_version_id": row.id,
                "dataset_hash": digest,
                "code_version_sha": code_version_sha,
                "compute_backend": compute_backend,
                "dagster_asset_key": dagster_asset_key,
                "datahub_urn": datahub_urn,
            }
    except Exception:
        logger.warning("dataset lineage registration skipped", exc_info=True)
        return {}


def register_iceberg_dataset(
    *,
    iceberg_identifier: str,
    name: str | None = None,
    provider: str = "iceberg",
    domain: str = "user.dataset",
    sample_df: pd.DataFrame | None = None,
    source_uri: str | None = None,
    storage_uri: str | None = None,
    load_mode: str = "managed",
    llm_annotations: dict[str, Any] | None = None,
    column_docs: list[dict[str, Any]] | None = None,
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    row_count: int | None = None,
    file_count: int | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    """Persist a catalog row + version for an Iceberg-backed dataset.

    ``sample_df`` may be ``None`` for tables that have just been created
    but not yet annotated; we still write a catalog row so the UI can
    show "discovered" datasets immediately.
    """
    catalog_name = name or iceberg_identifier
    full_meta: dict[str, Any] = {
        "iceberg_identifier": iceberg_identifier,
        "truncated": bool(truncated),
        **(meta or {}),
    }
    if sample_df is None or sample_df.empty:
        sample_df = pd.DataFrame({"_sentinel": [None]})
    return register_dataset_version(
        name=catalog_name,
        provider=provider,
        domain=domain,
        df=sample_df,
        storage_uri=storage_uri,
        meta=full_meta,
        tags=tags,
        file_count=file_count,
        iceberg_identifier=iceberg_identifier,
        load_mode=load_mode,
        source_uri=source_uri,
        llm_annotations=llm_annotations,
        column_docs=column_docs,
    )


def _polymorphic_identity_for(sym: Symbol) -> tuple[str, type | None]:
    """Pick the right ``(instrument_class, ORM class)`` for a :class:`Symbol`.

    Returns a pair of ``(discriminator, orm_cls)`` where ``discriminator`` is
    the string written to ``instruments.instrument_class`` (and to
    SQLAlchemy's ``polymorphic_identity``) and ``orm_cls`` is the concrete
    joined-table subclass (or ``None`` for the bare :class:`Instrument`
    shape when the symbol doesn't cleanly map to a rich subclass).

    The mapping:

    - ``SecurityType.EQUITY``   → ``InstrumentEquity`` / ``spot``
    - ``SecurityType.OPTION``   → ``InstrumentOption`` / ``option``
    - ``SecurityType.FUTURE``   → ``InstrumentFuture`` / ``future``
    - ``SecurityType.FOREX``    → ``InstrumentFxPair`` / ``fx_pair``
    - ``SecurityType.CRYPTO``/``CRYPTO_FUTURE`` → ``InstrumentCrypto``
    - ``SecurityType.CFD``      → ``InstrumentCfd`` / ``cfd``
    - ``SecurityType.INDEX``    → ``InstrumentIndex`` / ``index``
    - ``SecurityType.COMMODITY``→ ``InstrumentCommodity`` / ``spot_commodity``

    Anything else falls back to the plain ``Instrument`` row.
    """
    from aqp.core.types import SecurityType
    from aqp.persistence.models_instruments import (
        InstrumentCfd,
        InstrumentCommodity,
        InstrumentCrypto,
        InstrumentEquity,
        InstrumentFuture,
        InstrumentFxPair,
        InstrumentIndex,
        InstrumentOption,
    )

    mapping: dict[SecurityType, tuple[str, type]] = {
        SecurityType.EQUITY: ("spot", InstrumentEquity),
        SecurityType.OPTION: ("option", InstrumentOption),
        SecurityType.FUTURE: ("future", InstrumentFuture),
        SecurityType.FOREX: ("fx_pair", InstrumentFxPair),
        SecurityType.CRYPTO: ("crypto_token", InstrumentCrypto),
        SecurityType.CRYPTO_FUTURE: ("crypto_token", InstrumentCrypto),
        SecurityType.CFD: ("cfd", InstrumentCfd),
        SecurityType.INDEX: ("index", InstrumentIndex),
        SecurityType.INDEX_OPTION: ("option", InstrumentOption),
        SecurityType.COMMODITY: ("spot_commodity", InstrumentCommodity),
        SecurityType.FUTURE_OPTION: ("option", InstrumentOption),
    }
    hit = mapping.get(sym.security_type)
    if hit is None:
        return ("", None)
    return hit


def _upsert_instruments(session, vt_symbols: list[str]) -> None:
    """Upsert :class:`Instrument` rows for each ``vt_symbol``.

    When :func:`_polymorphic_identity_for` returns a concrete subclass,
    we instantiate that subclass instead of the bare ``Instrument`` so the
    joined-table subclass row is created alongside the parent. Legacy rows
    (``instrument_class IS NULL``) remain valid and are left untouched.
    """
    if not vt_symbols:
        return
    existing_rows = session.execute(
        select(Instrument).where(Instrument.vt_symbol.in_(vt_symbols))
    ).scalars().all()
    existing = {row.vt_symbol: row for row in existing_rows}
    for vt_symbol in vt_symbols:
        sym = Symbol.parse(vt_symbol)
        discriminator, orm_cls = _polymorphic_identity_for(sym)
        row = existing.get(vt_symbol)
        if row is None:
            kwargs = dict(
                vt_symbol=vt_symbol,
                ticker=sym.ticker,
                exchange=sym.exchange.value,
                asset_class=sym.asset_class.value,
                security_type=sym.security_type.value,
                identifiers={"vt_symbol": vt_symbol, "ticker": sym.ticker},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            if discriminator:
                kwargs["instrument_class"] = discriminator
            target_cls = orm_cls or Instrument
            row = target_cls(**kwargs)
            session.add(row)
            continue
        row.ticker = row.ticker or sym.ticker
        row.exchange = row.exchange or sym.exchange.value
        row.asset_class = row.asset_class or sym.asset_class.value
        row.security_type = row.security_type or sym.security_type.value
        if discriminator and not row.instrument_class:
            row.instrument_class = discriminator
        row.updated_at = datetime.utcnow()
        session.add(row)


def upsert_instruments_for_vt_symbols(vt_symbols: Iterable[str]) -> None:
    """Best-effort: ensure :class:`~aqp.persistence.models.Instrument` rows exist.

    Used when OHLCV is written without going through :func:`register_dataset_version`
    (for example batched ingest with ``register_catalog_version=False``) so the
    Data Browser and ``/data/universe?source=catalog`` stay aligned with the lake.
    """
    vt_list = sorted({str(v).strip().upper() for v in vt_symbols if str(v).strip()})
    if not vt_list:
        return
    try:
        with get_session() as session:
            _upsert_instruments(session, vt_list)
    except Exception:
        logger.warning("instrument upsert for vt_symbols failed", exc_info=True)


def _schema_snapshot(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "columns": list(df.columns),
        "dtypes": {c: str(dt) for c, dt in df.dtypes.items()},
    }


def _dataset_hash(df: pd.DataFrame) -> str:
    buf = pd.util.hash_pandas_object(df, index=False).values.tobytes()
    return hashlib.sha256(buf).hexdigest()


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except Exception:
        return None


def register_data_links(
    *,
    dataset_version_id: str,
    source_name: str | None,
    entity_rows: Iterable[dict[str, Any]],
) -> list[str]:
    """Emit :class:`DataLink` rows for a materialised dataset version.

    ``entity_rows`` is an iterable of dicts with at least
    ``entity_kind``, ``entity_id``, optionally ``instrument_vt_symbol``
    (or ``instrument_id``), ``coverage_start``, ``coverage_end``,
    ``row_count``, and ``meta``. Returns the list of persisted
    ``data_links.id`` values.

    Best-effort: failures log and return ``[]`` so ingestion pipelines
    don't blow up if the DB is transiently unavailable.
    """
    rows = list(entity_rows or [])
    if not rows:
        return []
    try:
        with get_session() as session:
            source_id = _source_id(session, source_name)

            persisted: list[str] = []
            for entry in rows:
                entity_kind = str(entry.get("entity_kind") or "instrument")
                entity_id = str(entry.get("entity_id") or "").strip()
                if not entity_id:
                    continue

                instrument_id = entry.get("instrument_id")
                if not instrument_id:
                    vt_symbol = entry.get("instrument_vt_symbol") or (
                        entity_id if entity_kind == "instrument" else None
                    )
                    if vt_symbol:
                        instrument = session.execute(
                            select(Instrument).where(Instrument.vt_symbol == vt_symbol).limit(1)
                        ).scalar_one_or_none()
                        instrument_id = instrument.id if instrument else None

                row = DataLink(
                    dataset_version_id=dataset_version_id,
                    source_id=source_id,
                    entity_kind=entity_kind,
                    entity_id=entity_id,
                    instrument_id=instrument_id,
                    coverage_start=_to_dt(entry.get("coverage_start")),
                    coverage_end=_to_dt(entry.get("coverage_end")),
                    row_count=int(entry.get("row_count") or 0),
                    meta=dict(entry.get("meta") or {}),
                    created_at=datetime.utcnow(),
                )
                session.add(row)
                session.flush()
                persisted.append(row.id)
            return persisted
    except Exception:
        logger.warning("register_data_links skipped", exc_info=True)
        return []


def _source_id(session: Any, name: str | None) -> str | None:
    if not name:
        return None
    row = session.execute(
        select(DataSource).where(DataSource.name == name).limit(1)
    ).scalar_one_or_none()
    return row.id if row else None
