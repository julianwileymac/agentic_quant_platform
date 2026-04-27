"""Data catalog and lineage persistence helpers."""
from __future__ import annotations

import logging
import hashlib
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import func, select

from aqp.core.types import Symbol
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    DataLink,
    DataSource,
    DatasetCatalog,
    DatasetVersion,
    Instrument,
)

logger = logging.getLogger(__name__)


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
) -> dict[str, Any]:
    """Persist a dataset catalog/version row and return lineage ids.

    The helper is intentionally best-effort: if the DB is unavailable, we log
    and return an empty mapping so ingestion still succeeds.

    For non-OHLCV (``domain != "market.bars"``) datasets the ``vt_symbol``
    / ``timestamp`` extraction and instrument upsert paths are skipped so
    generic Iceberg tables don't blow up on missing columns.
    """
    if df is None or df.empty:
        return {}

    is_market_bars = (domain or "").startswith("market.bars")

    try:
        if is_market_bars:
            ts = pd.to_datetime(df.get("timestamp"), errors="coerce")
            start_time = _to_dt(ts.min())
            end_time = _to_dt(ts.max())
            vt_symbols = sorted(
                df.get("vt_symbol", pd.Series(dtype=str)).dropna().astype(str).unique().tolist()
            )
        else:
            start_time = end_time = None
            vt_symbols = []
        schema = _schema_snapshot(df)
        digest = dataset_hash_value or _dataset_hash(df)

        with get_session() as session:
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
                catalog.updated_at = datetime.utcnow()
                session.add(catalog)

            current_version = (
                session.execute(
                    select(func.max(DatasetVersion.version)).where(DatasetVersion.catalog_id == catalog.id)
                ).scalar_one()
                or 0
            )
            row = DatasetVersion(
                catalog_id=catalog.id,
                version=int(current_version) + 1,
                status="active",
                as_of=as_of or datetime.utcnow(),
                start_time=start_time,
                end_time=end_time,
                row_count=int(len(df)),
                symbol_count=int(len(vt_symbols)),
                file_count=int(file_count or len(vt_symbols) or 1),
                dataset_hash=digest,
                materialization_uri=storage_uri,
                columns=list(df.columns),
                schema_json=schema,
                meta=dict(meta or {}),
                created_at=datetime.utcnow(),
            )
            session.add(row)
            if is_market_bars:
                _upsert_instruments(session, vt_symbols)
            session.flush()
            return {
                "dataset_catalog_id": catalog.id,
                "dataset_version_id": row.id,
                "dataset_hash": digest,
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
