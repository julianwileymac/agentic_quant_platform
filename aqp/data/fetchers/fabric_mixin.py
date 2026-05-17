"""Optional fabric mixin for Fetcher subclasses.

Layers canonical schema validation, idempotency, observability, and a
sanctioned Iceberg persist path on top of the existing Fetcher contract.
The mixin is opt-in: existing fetchers continue to work without it.

Usage:
    class MyFetcher(Fetcher, FabricFetcherMixin):
        CANONICAL_SCHEMA_CLASS = OHLCVSchema
        SUPPORTED_INTERVALS = ("1m", "5m", "1d")
        REQUIRES_AUTH = True
        PROVIDER_NAME = "MyProvider"

        def fetch(self, ctx): ...

The mixin's metaclass is FabricObjectMeta so concrete subclasses register
into FABRIC_REGISTRY automatically. The existing @register_source_fetcher
decorator on the same class continues to handle engine registration.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from aqp.credentials import CredentialKey, get_resolver
from aqp.data.catalog.lineage import record_lineage
from aqp.data.fabric.identity import FabricHashMixin, FabricIdentity, FabricObjectMeta
from aqp.data.fabric.schema_registry import CanonicalSchemaBase, SchemaValidationError
from aqp.observability.fabric_bus import get_observability_bus, instrument_loader

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd
    import pyarrow as pa

    from aqp.data.catalog.active_metadata import BusinessMetadata

logger = logging.getLogger(__name__)

MedallionLayer = Literal["bronze", "silver", "gold"]


class FabricFetcherMixin(FabricIdentity, metaclass=FabricObjectMeta):
    """Opt-in helper for canonical-schema-aware fetchers."""

    __abstract_fabric__ = True

    CANONICAL_SCHEMA_CLASS: ClassVar[type[CanonicalSchemaBase]]
    SUPPORTED_INTERVALS: ClassVar[tuple[str, ...]]
    REQUIRES_AUTH: ClassVar[bool] = False
    PROVIDER_NAME: ClassVar[str]
    MEDALLION_LAYER: ClassVar[MedallionLayer] = "bronze"
    LOADER_SCHEMA_METADATA: ClassVar[dict[str, Any]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Use cls.__dict__ so the abstract flag isn't inherited from the mixin.
        if cls is FabricFetcherMixin or cls.__dict__.get("__abstract_fabric__", False):
            return

        required_attrs = ("CANONICAL_SCHEMA_CLASS", "SUPPORTED_INTERVALS", "PROVIDER_NAME")
        missing = [name for name in required_attrs if not hasattr(cls, name)]
        if missing:
            raise TypeError(
                f"{cls.__module__}.{cls.__qualname__} missing required class attrs: "
                f"{', '.join(missing)}"
            )

        schema_cls = getattr(cls, "CANONICAL_SCHEMA_CLASS")
        if not isinstance(schema_cls, type) or not issubclass(schema_cls, CanonicalSchemaBase):
            raise TypeError(
                f"{cls.__module__}.{cls.__qualname__}.CANONICAL_SCHEMA_CLASS must subclass "
                "CanonicalSchemaBase"
            )

        intervals = tuple(str(value) for value in getattr(cls, "SUPPORTED_INTERVALS", ()))
        cls.SUPPORTED_INTERVALS = intervals
        cls.LOADER_SCHEMA_METADATA = {
            "class": cls.__qualname__,
            "provider": str(getattr(cls, "PROVIDER_NAME")),
            "source_category": "fetcher",
            "canonical_schema": schema_cls.__name__,
            "supported_intervals": intervals,
            "requires_auth": bool(getattr(cls, "REQUIRES_AUTH", False)),
            "medallion_layer": str(getattr(cls, "MEDALLION_LAYER", "bronze")),
        }
        instrument_loader(cls)

    def _compute_request_hash(
        self,
        *,
        edge_ids: Sequence[str],
        time_window: tuple[datetime, datetime] | None,
    ) -> str:
        """Return deterministic SHA-256 request fingerprint."""

        def _to_iso_utc(value: datetime) -> str:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            else:
                value = value.astimezone(timezone.utc)
            return value.isoformat().replace("+00:00", "Z")

        data_source_id = str(
            getattr(self, "data_source_id", None)
            or getattr(self, "feed_id", None)
            or getattr(self, "provider_name", None)
            or self.PROVIDER_NAME.lower()
        )

        normalized_window: tuple[str, str] | None = None
        if time_window is not None:
            start, end = time_window
            if end < start:
                start, end = end, start
            normalized_window = (_to_iso_utc(start), _to_iso_utc(end))

        payload = {
            "data_source_id": data_source_id,
            "edge_ids": sorted(str(edge_id) for edge_id in edge_ids),
            "window_iso": normalized_window,
        }
        return FabricHashMixin.compute_dict_hash(payload)

    def _idempotency_check(self, request_hash: str) -> bool:
        """Return True when a prior SUCCESS row already exists."""
        from aqp.persistence.db import get_session
        from aqp.persistence.models_ingestion_ledger import IngestionLedgerRow

        try:
            with get_session() as session:
                existing = (
                    session.query(IngestionLedgerRow)
                    .filter_by(request_hash=request_hash, execution_status="SUCCESS")
                    .first()
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "idempotency check failed provider=%s hash=%s (%s)",
                self.PROVIDER_NAME,
                request_hash,
                exc,
            )
            return False

        if existing is None:
            return False

        get_observability_bus().hash_collisions.add(
            1,
            attributes={"provider": self.PROVIDER_NAME},
        )
        return True

    def _resolve_credentials(self) -> dict[str, str]:
        """Resolve fetcher credentials through the configured resolver chain."""
        credential = get_resolver().resolve(
            CredentialKey(service=self.PROVIDER_NAME.lower(), purpose="fetcher"),
            required=self.REQUIRES_AUTH,
        )
        return {str(key): str(value) for key, value in credential.fields.items()}

    def normalize_schema(
        self,
        raw: "pd.DataFrame | pa.Table | list[dict[str, Any]]",
    ) -> "pa.Table":
        """Coerce raw payloads into the canonical Arrow schema."""
        import pyarrow as pa

        table: pa.Table
        if isinstance(raw, pa.Table):
            table = raw
        elif isinstance(raw, list):
            table = pa.Table.from_pylist([dict(row) for row in raw])
        else:
            import pandas as pd

            frame: pd.DataFrame
            if isinstance(raw, pd.DataFrame):
                frame = raw
            elif hasattr(raw, "to_pandas") and callable(getattr(raw, "to_pandas")):
                frame = raw.to_pandas()
            else:
                frame = pd.DataFrame(raw)
            table = pa.Table.from_pandas(frame, preserve_index=False)

        try:
            return self.CANONICAL_SCHEMA_CLASS.validate_table(table)
        except SchemaValidationError:
            get_observability_bus().schema_errors.add(
                1,
                attributes={"provider": self.PROVIDER_NAME},
            )
            raise

    def persist_to_iceberg(
        self,
        table: "pa.Table",
        *,
        namespace: str,
        table_name: str,
        business_metadata: "BusinessMetadata",
        medallion_layer: str | None = None,
        mode: Literal["append", "create_or_replace"] = "append",
    ) -> int:
        """Persist a canonical table through the sanctioned Iceberg wrapper.

        Routes through :func:`aqp.data.iceberg_catalog.append_arrow` (Hard Rule 3)
        with mandatory medallion_layer + BusinessMetadata (Hard Rule 21).

        ``medallion_layer`` may be provided per-call; if omitted, defaults to
        the class attribute :attr:`MEDALLION_LAYER`.
        """
        from aqp.data.iceberg_catalog import append_arrow, create_or_replace_table

        layer = medallion_layer or self.MEDALLION_LAYER
        identifier = f"{namespace}.{table_name}"
        if mode == "append":
            append_arrow(
                identifier=identifier,
                table=table,
                medallion_layer=layer,
                business_metadata=business_metadata,
            )
        elif mode == "create_or_replace":
            create_or_replace_table(identifier=identifier, arrow_schema=table.schema)
            append_arrow(
                identifier=identifier,
                table=table,
                create_if_missing=False,
                medallion_layer=layer,
                business_metadata=business_metadata,
            )
        else:
            raise ValueError(f"unsupported persist mode: {mode!r}")

        rows_written = int(table.num_rows)
        get_observability_bus().records_persisted.add(
            rows_written,
            attributes={"provider": self.PROVIDER_NAME},
        )
        record_lineage(
            transform_kind="ingest.persist",
            target=identifier,
            actor=self.PROVIDER_NAME,
            rows_written=rows_written,
            medallion_layer=self.MEDALLION_LAYER,
        )
        return rows_written

    def to_airbyte_stream(self) -> dict[str, Any]:
        from aqp.data.airbyte.orchestrator import AirbyteOrchestrator

        return AirbyteOrchestrator().build_stream_config(self)

    def to_dagster_asset(self) -> Any:
        from aqp.dagster.asset_factory import DagsterAssetFactory

        return DagsterAssetFactory().build_asset(self)


__all__ = ["FabricFetcherMixin"]
