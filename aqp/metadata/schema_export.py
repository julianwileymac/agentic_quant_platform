"""Multi-format schema exporter for AQP OpenMetadata Pydantic models."""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import logging
import pkgutil
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, ClassVar, Literal, Union, get_args, get_origin
from uuid import UUID

from pydantic.fields import FieldInfo, PydanticUndefined

from aqp.metadata.openmetadata.base import AQPOpenMetadataBase

logger = logging.getLogger(__name__)

_JSON_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
_PDL_NAMESPACE = "com.aqp.models.metadata"
_SUPPORTED_FORMATS = ("json", "avro", "pdl")


@dataclass(frozen=True, slots=True)
class _PDLField:
    """Template-ready representation of a single PDL field."""

    name: str
    pdl_type: str
    optional: bool
    default_repr: str | None
    description: str | None
    avro_annotation: str | None


@dataclass(frozen=True, slots=True)
class _PDLRecord:
    """Template-ready representation of a nested PDL record."""

    name: str
    fields: list[_PDLField]


class SchemaExporter:
    """Export OpenMetadata models as JSON Schema, AVRO, and PDL."""

    OUTPUT_DIRS: ClassVar[dict[str, Path]] = {
        "json": Path("schemas/json"),
        "avro": Path("schemas/avro"),
        "pdl": Path("schemas/pdl"),
    }

    def __init__(self, *, output_root: Path | None = None) -> None:
        """Initialise an exporter rooted at ``output_root``."""
        self.output_root = output_root or Path.cwd()

    def discover_models(self) -> list[type[AQPOpenMetadataBase]]:
        """Discover concrete ``AQPOpenMetadataBase`` subclasses in OpenMetadata package."""
        package_name = "aqp.metadata.openmetadata"
        package = importlib.import_module(package_name)
        modules = [package]
        if hasattr(package, "__path__"):
            for module_info in pkgutil.iter_modules(package.__path__, f"{package_name}."):
                modules.append(importlib.import_module(module_info.name))

        discovered: set[type[AQPOpenMetadataBase]] = set()
        for module in modules:
            for _, candidate in inspect.getmembers(module, inspect.isclass):
                if not issubclass(candidate, AQPOpenMetadataBase):
                    continue
                if candidate is AQPOpenMetadataBase:
                    continue
                discovered.add(candidate)

        return sorted(discovered, key=lambda model_cls: model_cls.__name__)

    def export_json_schema(self, model: type[AQPOpenMetadataBase]) -> Path:
        """Export one model to JSON Schema and return the file path."""
        schema = model.model_json_schema()
        entity_type = getattr(model, "entity_type", None)
        aspect_name = getattr(model, "aspect_name", None)
        if entity_type:
            schema["x-aqp-entity-type"] = entity_type
        if aspect_name:
            schema["x-aqp-aspect-name"] = aspect_name
        schema.setdefault("$schema", _JSON_SCHEMA_DRAFT)

        output_path = self._ensure_output_dir("json") / f"{model.__name__}.schema.json"
        self._write_json(output_path, schema)
        return output_path

    def export_avro(self, model: type[AQPOpenMetadataBase]) -> Path:
        """Export one model to AVRO and return the file path."""
        schema = self._build_avro_schema(model)
        self._ensure_avro_logical_types(schema, model)
        schema["namespace"] = _PDL_NAMESPACE

        output_path = self._ensure_output_dir("avro") / f"{model.__name__}.avsc"
        self._write_json(output_path, schema)
        return output_path

    def export_pdl(self, model: type[AQPOpenMetadataBase]) -> Path:
        """Export one model to DataHub-style PDL and return the file path."""
        template = self._load_pdl_template()
        nested_models = self._collect_nested_models(model)
        nested_records = [
            self._build_pdl_record(nested_model)
            for nested_model in sorted(
                (nested for nested in nested_models if nested is not model),
                key=lambda nested: nested.__name__,
            )
        ]

        context = {
            "namespace": _PDL_NAMESPACE,
            "model_name": model.__name__,
            "aspect_name": getattr(model, "aspect_name", None),
            "entity_type": getattr(model, "entity_type", None),
            "record_doc": inspect.cleandoc(model.__doc__ or "") or None,
            "fields": self._build_pdl_fields(model),
            "nested_records": nested_records,
        }
        rendered = template.render(**context).strip() + "\n"
        output_path = self._ensure_output_dir("pdl") / f"{model.__name__}.pdl"
        output_path.write_text(rendered, encoding="utf-8")
        return output_path

    def export_all(self) -> dict[str, list[Path]]:
        """Export all discovered models to every supported schema format."""
        models = self.discover_models()
        logger.info("Discovered %d OpenMetadata models.", len(models))
        outputs: dict[str, list[Path]] = {fmt: [] for fmt in _SUPPORTED_FORMATS}
        for model in models:
            outputs["json"].append(self.export_json_schema(model))
            outputs["avro"].append(self.export_avro(model))
            outputs["pdl"].append(self.export_pdl(model))
        return outputs

    def _ensure_output_dir(self, fmt: str) -> Path:
        """Create and return output directory for one format."""
        output_dir = self.output_root / self.OUTPUT_DIRS[fmt]
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _build_avro_schema(self, model: type[AQPOpenMetadataBase]) -> dict[str, Any]:
        """Build AVRO schema dict for a Pydantic model."""
        try:
            from pydantic_avro.base import AvroBase
        except ImportError as exc:
            raise RuntimeError(
                "pydantic-avro is required for AVRO export. Install with "
                "`pip install pydantic-avro`."
            ) from exc

        schema_builder = getattr(AvroBase, "avro_schema_for_pydantic_class", None)
        if callable(schema_builder):
            # Preferred path: use the native helper when exposed by this pydantic-avro version.
            schema = schema_builder(model)
        else:
            # Fallback path: mix AvroBase into the target model when helper is unavailable.
            avro_model = type(f"{model.__name__}Avro", (model, AvroBase), {})
            schema = avro_model.avro_schema()

        if isinstance(schema, str):
            return json.loads(schema)
        return dict(schema)

    def _ensure_avro_logical_types(
        self, schema: dict[str, Any], root_model: type[AQPOpenMetadataBase]
    ) -> None:
        """Defensively enforce logical-type hints for UUID/date/time/decimal fields."""
        record_index: dict[str, dict[str, Any]] = {}
        self._index_avro_records(schema, record_index)

        for model in self._collect_nested_models(root_model):
            record = record_index.get(model.__name__)
            if record is None:
                continue
            self._patch_record_logical_types(record, model)

    def _index_avro_records(self, node: Any, record_index: dict[str, dict[str, Any]]) -> None:
        """Collect AVRO record nodes by name."""
        if isinstance(node, dict):
            if node.get("type") == "record" and isinstance(node.get("name"), str):
                record_index[node["name"]] = node
            for value in node.values():
                self._index_avro_records(value, record_index)
        elif isinstance(node, list):
            for item in node:
                self._index_avro_records(item, record_index)

    def _patch_record_logical_types(
        self, record_schema: dict[str, Any], model: type[AQPOpenMetadataBase]
    ) -> None:
        """Patch one AVRO record schema using Pydantic field annotations."""
        fields = record_schema.get("fields")
        if not isinstance(fields, list):
            return
        for field_schema in fields:
            if not isinstance(field_schema, dict):
                continue
            field_name = field_schema.get("name")
            if not isinstance(field_name, str):
                continue
            field_info = model.model_fields.get(field_name)
            if field_info is None:
                continue
            field_schema["type"] = self._patch_schema_type(field_schema.get("type"), field_info.annotation)

    def _patch_schema_type(self, avro_type: Any, annotation: Any) -> Any:
        """Patch an AVRO type node based on the originating Python annotation."""
        annotation = self._strip_annotated(annotation)
        optional, union_members = self._split_optional(annotation)
        if optional and len(union_members) == 1:
            annotation = union_members[0]
        elif len(union_members) > 1 and isinstance(avro_type, list):
            patched_union: list[Any] = []
            for branch in avro_type:
                if branch == "null":
                    patched_union.append(branch)
                    continue
                patched = branch
                for member in union_members:
                    candidate = self._patch_schema_type(patched, member)
                    if candidate != patched:
                        patched = candidate
                        break
                patched_union.append(patched)
            return patched_union

        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin in {list, tuple, set, frozenset}:
            item_annotation = args[0] if args else Any
            if isinstance(avro_type, dict) and avro_type.get("type") == "array":
                avro_type["items"] = self._patch_schema_type(avro_type.get("items"), item_annotation)
            return avro_type
        if origin in {dict}:
            value_annotation = args[1] if len(args) > 1 else Any
            if isinstance(avro_type, dict) and avro_type.get("type") == "map":
                avro_type["values"] = self._patch_schema_type(avro_type.get("values"), value_annotation)
            return avro_type

        if inspect.isclass(annotation) and issubclass(annotation, AQPOpenMetadataBase):
            if isinstance(avro_type, dict) and avro_type.get("type") == "record":
                self._patch_record_logical_types(avro_type, annotation)
            return avro_type

        logical_type = self._logical_type_for(annotation)
        if logical_type is None:
            return avro_type
        primitive_type, logical_name = logical_type
        return self._apply_logical_type(avro_type, primitive_type, logical_name)

    def _logical_type_for(self, annotation: Any) -> tuple[str, str] | None:
        """Map selected Python types to AVRO primitive/logical type pairs."""
        if annotation is UUID:
            return ("string", "uuid")
        if annotation is datetime:
            return ("long", "timestamp-millis")
        if annotation is date:
            return ("int", "date")
        if annotation is Decimal:
            return ("bytes", "decimal")
        if inspect.isclass(annotation):
            if issubclass(annotation, UUID):
                return ("string", "uuid")
            if issubclass(annotation, datetime):
                return ("long", "timestamp-millis")
            if issubclass(annotation, date):
                return ("int", "date")
            if issubclass(annotation, Decimal):
                return ("bytes", "decimal")
        return None

    def _apply_logical_type(self, avro_type: Any, primitive_type: str, logical_type: str) -> Any:
        """Inject an AVRO logical type onto matching schema branches."""
        if isinstance(avro_type, str):
            if avro_type != primitive_type:
                return avro_type
            payload: dict[str, Any] = {"type": primitive_type, "logicalType": logical_type}
            if logical_type == "decimal":
                payload.setdefault("precision", 38)
                payload.setdefault("scale", 9)
            return payload

        if isinstance(avro_type, list):
            return [
                self._apply_logical_type(branch, primitive_type, logical_type)
                if branch != "null"
                else branch
                for branch in avro_type
            ]

        if isinstance(avro_type, dict):
            node_type = avro_type.get("type")
            if node_type == primitive_type:
                avro_type.setdefault("logicalType", logical_type)
                if logical_type == "decimal":
                    avro_type.setdefault("precision", 38)
                    avro_type.setdefault("scale", 9)
            elif isinstance(node_type, list):
                avro_type["type"] = [
                    self._apply_logical_type(branch, primitive_type, logical_type)
                    if branch != "null"
                    else branch
                    for branch in node_type
                ]
        return avro_type

    def _collect_nested_models(
        self, model: type[AQPOpenMetadataBase]
    ) -> set[type[AQPOpenMetadataBase]]:
        """Collect root + nested model classes reachable from field annotations."""
        collected: set[type[AQPOpenMetadataBase]] = set()
        self._walk_model_tree(model, collected)
        return collected

    def _walk_model_tree(
        self, model: type[AQPOpenMetadataBase], collected: set[type[AQPOpenMetadataBase]]
    ) -> None:
        """Walk nested model field annotations recursively."""
        if model in collected:
            return
        collected.add(model)
        for field in model.model_fields.values():
            for nested in self._models_from_annotation(field.annotation):
                self._walk_model_tree(nested, collected)

    def _models_from_annotation(self, annotation: Any) -> set[type[AQPOpenMetadataBase]]:
        """Extract nested ``AQPOpenMetadataBase`` classes from one annotation."""
        annotation = self._strip_annotated(annotation)
        origin = get_origin(annotation)
        if origin in {Union, UnionType}:
            nested: set[type[AQPOpenMetadataBase]] = set()
            for member in get_args(annotation):
                if member is type(None):
                    continue
                nested.update(self._models_from_annotation(member))
            return nested
        if origin in {list, tuple, set, frozenset, dict}:
            nested = set()
            for member in get_args(annotation):
                nested.update(self._models_from_annotation(member))
            return nested
        if inspect.isclass(annotation) and issubclass(annotation, AQPOpenMetadataBase):
            return {annotation}
        return set()

    def _build_pdl_record(self, model: type[AQPOpenMetadataBase]) -> _PDLRecord:
        """Build nested-record context for template rendering."""
        return _PDLRecord(name=model.__name__, fields=self._build_pdl_fields(model))

    def _build_pdl_fields(self, model: type[AQPOpenMetadataBase]) -> list[_PDLField]:
        """Build ordered PDL field contexts for one model."""
        rendered_fields: list[_PDLField] = []
        for name, field_info in model.model_fields.items():
            pdl_type, optional, avro_annotation = self._annotation_to_pdl(field_info.annotation)
            rendered_fields.append(
                _PDLField(
                    name=name,
                    pdl_type=pdl_type,
                    optional=optional,
                    default_repr=self._field_default_repr(field_info),
                    description=field_info.description,
                    avro_annotation=avro_annotation,
                )
            )
        return rendered_fields

    def _annotation_to_pdl(self, annotation: Any) -> tuple[str, bool, str | None]:
        """Map a Python annotation to ``(pdl_type, optional, avro_annotation)``."""
        annotation = self._strip_annotated(annotation)
        optional, union_members = self._split_optional(annotation)
        if optional and len(union_members) == 1:
            annotation = union_members[0]

        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin in {Union, UnionType}:
            return ("object", optional, None)
        if origin in {list, tuple, set, frozenset}:
            item_annotation = args[0] if args else Any
            item_type, _, _ = self._annotation_to_pdl(item_annotation)
            return (f"array[{item_type}]", optional, None)
        if origin in {dict}:
            key_annotation = args[0] if args else str
            value_annotation = args[1] if len(args) > 1 else Any
            key_type, _, _ = self._annotation_to_pdl(key_annotation)
            value_type, _, _ = self._annotation_to_pdl(value_annotation)
            key_type = "string" if key_type != "string" else key_type
            return (f"map[{key_type}, {value_type}]", optional, None)
        if origin is Literal:
            symbols = [self._literal_to_enum_symbol(value) for value in args]
            return (f"enum[{', '.join(symbols)}]", optional, None)

        if annotation is str:
            return ("string", optional, None)
        if annotation is int:
            return ("long", optional, None)
        if annotation is float:
            return ("double", optional, None)
        if annotation is bool:
            return ("boolean", optional, None)
        if annotation is datetime:
            return (
                "string",
                optional,
                '{"type":"long","logicalType":"timestamp-millis"}',
            )
        if annotation is date:
            return ("string", optional, '{"type":"int","logicalType":"date"}')
        if annotation is UUID:
            return ("string", optional, '{"type":"string","logicalType":"uuid"}')
        if annotation is Decimal:
            return (
                "string",
                optional,
                '{"type":"bytes","logicalType":"decimal","precision":38,"scale":9}',
            )
        if annotation is Any:
            return ("object", optional, None)
        if inspect.isclass(annotation) and issubclass(annotation, AQPOpenMetadataBase):
            return (annotation.__name__, optional, None)
        return ("object", optional, None)

    def _literal_to_enum_symbol(self, value: Any) -> str:
        """Convert literal values into deterministic enum-like symbols."""
        if isinstance(value, str):
            symbol = value.strip().upper().replace(" ", "_").replace("-", "_")
        else:
            symbol = str(value).strip().upper().replace(" ", "_").replace("-", "_")
        symbol = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in symbol)
        if not symbol:
            symbol = "UNKNOWN"
        if symbol[0].isdigit():
            symbol = f"VALUE_{symbol}"
        return symbol

    def _field_default_repr(self, field_info: FieldInfo) -> str | None:
        """Render Pydantic defaults to PDL-friendly literal strings."""
        if field_info.default is not PydanticUndefined:
            return self._value_to_pdl_literal(field_info.default)
        if field_info.default_factory is not None:
            try:
                produced = field_info.default_factory()
            except Exception:  # pragma: no cover - defensive for unusual factories
                return None
            return self._value_to_pdl_literal(produced)
        return None

    def _value_to_pdl_literal(self, value: Any) -> str:
        """Convert a Python value into a PDL-compatible literal string."""
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return json.dumps(value)
        if isinstance(value, str):
            return json.dumps(value)
        if isinstance(value, datetime):
            return json.dumps(value.isoformat())
        if isinstance(value, date):
            return json.dumps(value.isoformat())
        if isinstance(value, UUID):
            return json.dumps(str(value))
        if isinstance(value, Decimal):
            return json.dumps(str(value))
        if isinstance(value, (list, dict)):
            return json.dumps(value, sort_keys=True)
        return json.dumps(str(value))

    def _load_pdl_template(self):
        """Load and return the Jinja2 template used for PDL records."""
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError as exc:
            raise RuntimeError(
                "jinja2 is required for PDL export. Install with `pip install jinja2`."
            ) from exc

        templates_dir = Path(__file__).resolve().parent / "templates"
        environment = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
            lstrip_blocks=True,
            trim_blocks=True,
        )
        return environment.get_template("pdl_record.j2")

    def _strip_annotated(self, annotation: Any) -> Any:
        """Unwrap ``typing.Annotated`` shells."""
        while get_origin(annotation) is Annotated:
            annotation = get_args(annotation)[0]
        return annotation

    def _split_optional(self, annotation: Any) -> tuple[bool, tuple[Any, ...]]:
        """Split optional unions into ``(is_optional, non_none_members)``."""
        origin = get_origin(annotation)
        if origin not in {Union, UnionType}:
            return False, (annotation,)
        members = tuple(arg for arg in get_args(annotation) if arg is not type(None))
        return len(members) != len(get_args(annotation)), members

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Write indented JSON payload to disk."""
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")


def _print_summary(result: dict[str, list[Path]]) -> None:
    """Render export summary with Rich when available, otherwise log lines."""
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        logger.info("Schema export summary:")
        for fmt in _SUPPORTED_FORMATS:
            paths = result.get(fmt, [])
            logger.info("- %s: %d files", fmt, len(paths))
        return

    table = Table(title="Schema Export Summary")
    table.add_column("Format")
    table.add_column("Count", justify="right")
    table.add_column("Output Directory")
    for fmt in _SUPPORTED_FORMATS:
        paths = result.get(fmt, [])
        directory = str(paths[0].parent) if paths else "-"
        table.add_row(fmt, str(len(paths)), directory)
    Console().print(table)


def cli(argv: list[str] | None = None) -> int:
    """CLI entry point for exporting AQP metadata schemas."""
    parser = argparse.ArgumentParser(description="Export AQP OpenMetadata schemas.")
    parser.add_argument(
        "--format",
        choices=("json", "avro", "pdl", "all"),
        default="all",
        help="Export format.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Root directory where schemas/ will be written.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress summary output.",
    )
    args = parser.parse_args(argv)

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    exporter = SchemaExporter(output_root=args.output_root)
    try:
        if args.format == "all":
            result = exporter.export_all()
        else:
            models = exporter.discover_models()
            logger.info("Discovered %d OpenMetadata models.", len(models))
            result = {fmt: [] for fmt in _SUPPORTED_FORMATS}
            export_op = {
                "json": exporter.export_json_schema,
                "avro": exporter.export_avro,
                "pdl": exporter.export_pdl,
            }[args.format]
            result[args.format] = [export_op(model) for model in models]
        if not args.quiet:
            _print_summary(result)
        return 0
    except Exception:  # pragma: no cover - exercised by CLI runtime failures
        logger.exception("Schema export failed.")
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
