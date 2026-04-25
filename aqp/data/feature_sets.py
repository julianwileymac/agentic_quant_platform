"""Persistent named feature sets.

A :class:`FeatureSet` bundles :class:`aqp.data.indicators_zoo.IndicatorZoo`
specs (TA indicators + ``ModelPred:...`` prediction columns) under a
stable name so that backtests, training, live trading, and RL all
consume an identical feature panel.

This module owns:

- :class:`FeatureSetSpec` — validated Pydantic wrapper for list[str] specs.
- :class:`FeatureSetService` — thin SQLAlchemy CRUD + ``materialize()``.
- :class:`PersistedFeatureStore` — concrete :class:`aqp.core.interfaces.IFeatureStore`
  backed by the DB rows + :func:`IndicatorZoo.transform` materialization.

Materialised panels are cached on-disk under
``settings.data_dir / "feature_sets"`` keyed on
``sha256(feature_set_name + version + bars.hash)`` so re-materialising
the same panel for the same bars is a local-file hit.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.config import settings
from aqp.core.interfaces import IFeatureStore
from aqp.core.types import Symbol
from aqp.persistence.db import get_session
from aqp.persistence.models import (
    FeatureSet as FeatureSetRow,
    FeatureSetUsage,
    FeatureSetVersion,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FeatureSetSpec(BaseModel):
    """Typed wrapper — used by the API + wizard."""

    name: str
    description: str | None = None
    kind: str = "indicator"  # indicator | model_pred | composite
    specs: list[str] = Field(default_factory=list)
    default_lookback_days: int = 60
    tags: list[str] = Field(default_factory=list)


class FeatureSetSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    kind: str
    specs: list[str] = Field(default_factory=list)
    default_lookback_days: int
    tags: list[str] = Field(default_factory=list)
    version: int
    status: str
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class FeatureSetUsageRow(BaseModel):
    id: str
    feature_set_id: str
    version: int | None
    consumer_kind: str
    consumer_id: str | None
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_root() -> Path:
    root = Path(settings.data_dir) / "feature_sets"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _bars_fingerprint(bars: pd.DataFrame) -> str:
    """Deterministic lightweight hash of the input bars frame."""
    if bars.empty:
        return "empty"
    sub = bars[["timestamp", "vt_symbol"]].copy()
    ts = pd.to_datetime(sub["timestamp"]).astype("int64")
    vt = sub["vt_symbol"].astype(str)
    payload = f"{ts.min()}-{ts.max()}-{len(sub)}-{vt.nunique()}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _cache_key(name: str, version: int, specs: list[str], bars_fp: str) -> str:
    raw = json.dumps({"n": name, "v": version, "s": specs, "b": bars_fp}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FeatureSetService:
    """SQLAlchemy CRUD + materialisation for feature sets."""

    # --------------------------------------------------------- CRUD --

    def create(self, spec: FeatureSetSpec, *, created_by: str | None = None) -> FeatureSetSummary:
        with get_session() as session:
            existing = session.execute(
                select(FeatureSetRow).where(FeatureSetRow.name == spec.name)
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError(f"feature set {spec.name!r} already exists")
            row = FeatureSetRow(
                name=spec.name,
                description=spec.description,
                kind=spec.kind,
                specs=list(spec.specs),
                default_lookback_days=int(spec.default_lookback_days),
                tags=list(spec.tags),
                created_by=created_by,
                version=1,
                status="active",
            )
            session.add(row)
            session.flush()
            session.add(
                FeatureSetVersion(
                    feature_set_id=row.id,
                    version=1,
                    specs=list(spec.specs),
                    notes="initial",
                    created_by=created_by,
                )
            )
            return self._row_to_summary(row)

    def update(
        self,
        feature_set_id: str,
        spec: FeatureSetSpec,
        *,
        notes: str | None = None,
        created_by: str | None = None,
    ) -> FeatureSetSummary:
        with get_session() as session:
            row = session.get(FeatureSetRow, feature_set_id)
            if row is None:
                raise KeyError(f"no feature set {feature_set_id!r}")
            prev_specs = list(row.specs or [])
            new_specs = list(spec.specs)
            bumped = prev_specs != new_specs
            row.description = spec.description
            row.kind = spec.kind
            row.specs = new_specs
            row.default_lookback_days = int(spec.default_lookback_days)
            row.tags = list(spec.tags)
            row.updated_at = datetime.utcnow()
            if bumped:
                row.version = int(row.version or 1) + 1
                session.add(
                    FeatureSetVersion(
                        feature_set_id=row.id,
                        version=row.version,
                        specs=new_specs,
                        notes=notes,
                        created_by=created_by,
                    )
                )
            return self._row_to_summary(row)

    def delete(self, feature_set_id: str) -> None:
        with get_session() as session:
            row = session.get(FeatureSetRow, feature_set_id)
            if row is None:
                return
            row.status = "archived"
            row.updated_at = datetime.utcnow()

    def list(self, *, limit: int = 100, kind: str | None = None) -> list[FeatureSetSummary]:
        with get_session() as session:
            stmt = (
                select(FeatureSetRow)
                .where(FeatureSetRow.status == "active")
                .order_by(desc(FeatureSetRow.created_at))
                .limit(limit)
            )
            if kind:
                stmt = stmt.where(FeatureSetRow.kind == kind)
            rows = session.execute(stmt).scalars().all()
            return [self._row_to_summary(r) for r in rows]

    def get(self, feature_set_id: str) -> FeatureSetSummary | None:
        with get_session() as session:
            row = session.get(FeatureSetRow, feature_set_id)
            return self._row_to_summary(row) if row else None

    def get_by_name(self, name: str) -> FeatureSetSummary | None:
        with get_session() as session:
            row = session.execute(
                select(FeatureSetRow).where(FeatureSetRow.name == name)
            ).scalar_one_or_none()
            return self._row_to_summary(row) if row else None

    def versions(self, feature_set_id: str) -> list[dict[str, Any]]:
        with get_session() as session:
            rows = session.execute(
                select(FeatureSetVersion)
                .where(FeatureSetVersion.feature_set_id == feature_set_id)
                .order_by(desc(FeatureSetVersion.version))
            ).scalars().all()
            return [
                {
                    "id": r.id,
                    "version": r.version,
                    "specs": list(r.specs or []),
                    "notes": r.notes,
                    "created_by": r.created_by,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    # ---------------------------------------------------- Materialize --

    def materialize(
        self,
        feature_set_id: str,
        bars: pd.DataFrame,
        *,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Apply the specs of ``feature_set_id`` to ``bars`` and return the panel."""
        if bars.empty:
            return bars
        summary = self.get(feature_set_id)
        if summary is None:
            raise KeyError(f"no feature set {feature_set_id!r}")
        return self._materialize_with_specs(
            name=summary.name,
            version=summary.version,
            specs=summary.specs,
            bars=bars,
            use_cache=use_cache,
        )

    def materialize_by_name(
        self,
        name: str,
        bars: pd.DataFrame,
        *,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        summary = self.get_by_name(name)
        if summary is None:
            raise KeyError(f"no feature set named {name!r}")
        return self._materialize_with_specs(
            name=summary.name,
            version=summary.version,
            specs=summary.specs,
            bars=bars,
            use_cache=use_cache,
        )

    def materialize_ad_hoc(
        self,
        specs: list[str],
        bars: pd.DataFrame,
        *,
        use_cache: bool = False,
    ) -> pd.DataFrame:
        """Materialize a set of specs without persisting — used by /preview."""
        return self._materialize_with_specs(
            name="_preview",
            version=0,
            specs=list(specs or []),
            bars=bars,
            use_cache=use_cache,
        )

    def _materialize_with_specs(
        self,
        *,
        name: str,
        version: int,
        specs: list[str],
        bars: pd.DataFrame,
        use_cache: bool,
    ) -> pd.DataFrame:
        if bars.empty or not specs:
            # Still pass through IndicatorZoo to ensure schema consistency.
            specs = list(specs or [])
        fp = _bars_fingerprint(bars)
        cache_key = _cache_key(name, version, specs, fp)
        cache_path = _cache_root() / f"{cache_key}.parquet"
        if use_cache and cache_path.exists():
            try:
                return pd.read_parquet(cache_path)
            except Exception:
                logger.warning("feature_set cache read failed at %s", cache_path, exc_info=True)

        from aqp.data.indicators_zoo import IndicatorZoo

        zoo = IndicatorZoo()
        panel = zoo.transform(bars, indicators=specs or None)
        if use_cache:
            try:
                panel.to_parquet(cache_path, index=False)
            except Exception:
                logger.debug("feature_set cache write failed", exc_info=True)
        return panel

    # --------------------------------------------------------- Usages --

    def record_usage(
        self,
        feature_set_id: str,
        *,
        consumer_kind: str,
        consumer_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str | None:
        try:
            with get_session() as session:
                row = session.get(FeatureSetRow, feature_set_id)
                if row is None:
                    return None
                usage = FeatureSetUsage(
                    feature_set_id=feature_set_id,
                    version=row.version,
                    consumer_kind=consumer_kind,
                    consumer_id=consumer_id,
                    meta=dict(meta or {}),
                )
                session.add(usage)
                session.flush()
                return usage.id
        except Exception:
            logger.debug("feature_set usage write skipped", exc_info=True)
            return None

    def usages(
        self,
        feature_set_id: str,
        *,
        limit: int = 100,
    ) -> list[FeatureSetUsageRow]:
        with get_session() as session:
            rows = session.execute(
                select(FeatureSetUsage)
                .where(FeatureSetUsage.feature_set_id == feature_set_id)
                .order_by(desc(FeatureSetUsage.created_at))
                .limit(limit)
            ).scalars().all()
            return [
                FeatureSetUsageRow(
                    id=r.id,
                    feature_set_id=r.feature_set_id,
                    version=r.version,
                    consumer_kind=r.consumer_kind,
                    consumer_id=r.consumer_id,
                    meta=dict(r.meta or {}),
                    created_at=r.created_at,
                )
                for r in rows
            ]

    # --------------------------------------------------------- Helpers --

    @staticmethod
    def _row_to_summary(row: FeatureSetRow) -> FeatureSetSummary:
        return FeatureSetSummary(
            id=row.id,
            name=row.name,
            description=row.description,
            kind=row.kind,
            specs=list(row.specs or []),
            default_lookback_days=int(row.default_lookback_days or 60),
            tags=list(row.tags or []),
            version=int(row.version or 1),
            status=row.status,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# ---------------------------------------------------------------------------
# Persistence-backed IFeatureStore
# ---------------------------------------------------------------------------


class PersistedFeatureStore(IFeatureStore):
    """Concrete :class:`IFeatureStore` that materialises a named feature set.

    ``get_features((symbol, timestamp, feature_set_name))`` materialises
    the full panel on first call for the associated bars view and
    caches it in memory for the lifetime of the instance.
    """

    def __init__(
        self,
        bars: pd.DataFrame,
        service: FeatureSetService | None = None,
    ) -> None:
        self._bars = bars
        self._service = service or FeatureSetService()
        self._panels: dict[str, pd.DataFrame] = {}

    def get_features(
        self,
        symbol: Symbol,
        timestamp: datetime,
        feature_set: str,
    ) -> dict[str, float]:
        panel = self._panels.get(feature_set)
        if panel is None:
            panel = self._service.materialize_by_name(feature_set, self._bars)
            self._panels[feature_set] = panel
        vt = symbol.vt_symbol if hasattr(symbol, "vt_symbol") else str(symbol)
        mask = (panel["vt_symbol"] == vt) & (panel["timestamp"] <= pd.Timestamp(timestamp))
        sub = panel[mask].sort_values("timestamp")
        if sub.empty:
            return {}
        row = sub.iloc[-1].to_dict()
        out: dict[str, float] = {}
        for k, v in row.items():
            if k in ("timestamp", "vt_symbol", "open", "high", "low", "close", "volume"):
                continue
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out


__all__ = [
    "FeatureSetService",
    "FeatureSetSpec",
    "FeatureSetSummary",
    "FeatureSetUsageRow",
    "PersistedFeatureStore",
]
