from __future__ import annotations

from typing import ClassVar

import pyarrow as pa

from aqp.data.fabric.identity import FabricObjectMeta


class SchemaValidationError(ValueError):
    """Raised when a table cannot be validated against a canonical schema."""


SCHEMA_REGISTRY: dict[str, type[CanonicalSchemaBase]] = {}


def _type_predicate_signature(dtype: pa.DataType) -> str:
    signatures: list[str] = []
    for name in dir(pa.types):
        if not name.startswith("is_"):
            continue
        checker = getattr(pa.types, name)
        if not callable(checker):
            continue
        try:
            matched = bool(checker(dtype))
        except TypeError:
            continue
        if matched:
            signatures.append(name)
    return "|".join(sorted(signatures))


def _validate_parent_schema_compatibility(
    *,
    class_name: str,
    canonical_schema: pa.Schema,
    parent_schema: pa.Schema,
) -> None:
    for parent_field in parent_schema:
        if parent_field.name not in canonical_schema.names:
            raise TypeError(
                f"{class_name} is missing inherited field '{parent_field.name}' "
                "from PARENT_SCHEMA"
            )
        child_field = canonical_schema.field(parent_field.name)
        parent_sig = _type_predicate_signature(parent_field.type)
        child_sig = _type_predicate_signature(child_field.type)
        if parent_sig != child_sig:
            raise TypeError(
                f"{class_name}.{parent_field.name} is incompatible with parent schema: "
                f"{parent_field.type} vs {child_field.type}"
            )


class CanonicalSchemaMeta(FabricObjectMeta):
    """Metaclass that validates and registers canonical Arrow schemas."""

    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, object],
        **kwargs: object,
    ) -> type:
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)

        is_abstract = bool(namespace.get("__abstract_fabric__", False))
        if "__abstract_fabric__" not in namespace and any(
            getattr(base, "__abstract_fabric__", False) for base in bases
        ):
            is_abstract = False

        if is_abstract:
            return cls

        canonical_schema = getattr(cls, "CANONICAL_SCHEMA", None)
        if not isinstance(canonical_schema, pa.Schema):
            raise TypeError(
                f"{cls.__module__}.{cls.__qualname__} must declare "
                "CANONICAL_SCHEMA: ClassVar[pa.Schema]"
            )

        parent_schema = getattr(cls, "PARENT_SCHEMA", None)
        if parent_schema is not None:
            if not isinstance(parent_schema, pa.Schema):
                raise TypeError(f"{cls.__name__}.PARENT_SCHEMA must be a pyarrow.Schema")
            _validate_parent_schema_compatibility(
                class_name=cls.__name__,
                canonical_schema=canonical_schema,
                parent_schema=parent_schema,
            )

        SCHEMA_REGISTRY[cls.__name__] = cls
        return cls


class CanonicalSchemaBase(metaclass=CanonicalSchemaMeta):
    __abstract_fabric__ = True

    CANONICAL_SCHEMA: ClassVar[pa.Schema]
    PARENT_SCHEMA: ClassVar[pa.Schema | None] = None
    SCHEMA_VERSION: ClassVar[int] = 1

    @classmethod
    def validate_table(cls, table: pa.Table) -> pa.Table:
        if table.num_rows == 0:
            return table.cast(cls.CANONICAL_SCHEMA)

        for field in cls.CANONICAL_SCHEMA:
            if field.name not in table.column_names:
                raise SchemaValidationError(
                    f"{cls.__name__} validation failed; missing field '{field.name}'"
                )

        try:
            table = table.cast(cls.CANONICAL_SCHEMA)
        except pa.lib.ArrowInvalid as exc:
            raise SchemaValidationError(
                f"{cls.__name__} validation failed: {exc}"
            ) from exc
        return table

    @classmethod
    def evolution_diff(cls) -> dict[str, list[str]]:
        parent_schema = cls.PARENT_SCHEMA or pa.schema([])
        current_schema = cls.CANONICAL_SCHEMA

        parent_fields = {field.name: field for field in parent_schema}
        current_fields = {field.name: field for field in current_schema}

        added = sorted(name for name in current_fields if name not in parent_fields)
        removed = sorted(name for name in parent_fields if name not in current_fields)
        type_changed = sorted(
            name
            for name in (set(parent_fields) & set(current_fields))
            if parent_fields[name].type != current_fields[name].type
        )
        return {
            "added": added,
            "removed": removed,
            "type_changed": type_changed,
        }


class OHLCVSchema(CanonicalSchemaBase):
    SCHEMA_VERSION = 1
    CANONICAL_SCHEMA = pa.schema(
        [
            pa.field("symbol", pa.string()),
            pa.field("source_feed_id", pa.string()),
            pa.field("timestamp", pa.timestamp("us", tz="UTC")),
            pa.field("open", pa.float64()),
            pa.field("high", pa.float64()),
            pa.field("low", pa.float64()),
            pa.field("close", pa.float64()),
            pa.field("volume", pa.float64()),
        ]
    )


class MacroIndicatorSchema(CanonicalSchemaBase):
    SCHEMA_VERSION = 1
    CANONICAL_SCHEMA = pa.schema(
        [
            pa.field("series_id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("observation_date", pa.timestamp("us", tz="UTC")),
            pa.field("vintage_date", pa.timestamp("us", tz="UTC"), nullable=True),
            pa.field("revision_number", pa.int32()),
            pa.field("value", pa.float64()),
        ]
    )


class TickSchema(CanonicalSchemaBase):
    SCHEMA_VERSION = 1
    CANONICAL_SCHEMA = pa.schema(
        [
            pa.field("symbol", pa.string()),
            pa.field("exchange_ts", pa.timestamp("ns", tz="UTC")),
            pa.field("receive_ts", pa.timestamp("ns", tz="UTC")),
            pa.field("price", pa.float64()),
            pa.field("size", pa.float64()),
            pa.field("side", pa.string()),
            pa.field("exchange", pa.string()),
            pa.field("tape", pa.string()),
        ]
    )


class FundamentalsSchema(CanonicalSchemaBase):
    SCHEMA_VERSION = 1
    CANONICAL_SCHEMA = pa.schema(
        [
            pa.field("symbol", pa.string()),
            pa.field("source", pa.string()),
            pa.field("report_date", pa.timestamp("us", tz="UTC")),
            pa.field("fiscal_period", pa.string()),
            pa.field("market_cap", pa.float64()),
            pa.field("pe_ratio", pa.float64()),
            pa.field("eps", pa.float64()),
        ]
    )


class FeatureSchema(CanonicalSchemaBase):
    SCHEMA_VERSION = 1
    CANONICAL_SCHEMA = pa.schema(
        [
            pa.field("symbol", pa.string()),
            pa.field("feature_name", pa.string()),
            pa.field("computation_ts", pa.timestamp("us", tz="UTC")),
            pa.field("pipeline_version", pa.string()),
            pa.field("feature_value", pa.float64()),
        ]
    )


class InstrumentMetaSchema(CanonicalSchemaBase):
    """Portable schema for instrument metadata rows.

    ``metadata`` is stored as a JSON-encoded string for backend portability:
    PyIceberg struct support remains uneven across some deployments.
    """

    SCHEMA_VERSION = 1
    CANONICAL_SCHEMA = pa.schema(
        [
            pa.field("symbol_uuid", pa.string()),
            pa.field("universal_ticker", pa.string()),
            pa.field("asset_class", pa.string()),
            pa.field("exchange_code", pa.string()),
            pa.field("content_hash", pa.string()),
            pa.field("schema_version", pa.int32()),
            pa.field("metadata", pa.string()),
        ]
    )


__all__ = [
    "SCHEMA_REGISTRY",
    "CanonicalSchemaBase",
    "CanonicalSchemaMeta",
    "FeatureSchema",
    "FundamentalsSchema",
    "InstrumentMetaSchema",
    "MacroIndicatorSchema",
    "OHLCVSchema",
    "SchemaValidationError",
    "TickSchema",
]
