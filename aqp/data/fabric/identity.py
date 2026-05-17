from __future__ import annotations

import base64
import hashlib
import json
import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Any, ClassVar, Self

from aqp.data.catalog.lineage import LineageEvent

logger = logging.getLogger(__name__)


class FabricContractError(TypeError):
    """Raised when a concrete class violates a declared fabric contract."""


# The prompt's ``LineageRef`` concept maps directly to AQP's existing
# lineage event primitive.
LineageRef = LineageEvent


@dataclass(frozen=True, slots=True, init=False)
class VersionVector:
    """Deterministic vector-clock representation."""

    clock: tuple[tuple[str, int], ...]

    def __init__(self, clock: Mapping[str, int] | None = None) -> None:
        items: list[tuple[str, int]] = []
        for component, counter in (clock or {}).items():
            items.append((str(component), int(counter)))
        items.sort(key=lambda item: item[0])
        object.__setattr__(self, "clock", tuple(items))

    def get(self, component: str) -> int:
        for key, value in self.clock:
            if key == component:
                return value
        return 0

    def incremented(self, component: str) -> VersionVector:
        state = self.to_dict()
        state[component] = state.get(component, 0) + 1
        return VersionVector(state)

    def merge(self, other: VersionVector) -> VersionVector:
        merged = self.to_dict()
        for component, counter in other.clock:
            merged[component] = max(merged.get(component, 0), int(counter))
        return VersionVector(merged)

    def dominates(self, other: VersionVector) -> bool:
        mine = self.to_dict()
        for component, counter in other.clock:
            if mine.get(component, 0) < int(counter):
                return False
        return True

    def to_dict(self) -> dict[str, int]:
        return {component: int(counter) for component, counter in self.clock}


def _json_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, uuid.UUID):
        return value.hex
    if isinstance(value, Enum):
        return _canonicalize(value.value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(value[key])
            for key in sorted(value.keys(), key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        canonical_items = [_canonicalize(item) for item in value]
        return sorted(canonical_items, key=_json_sort_key)
    if is_dataclass(value):
        return _canonicalize(asdict(value))
    to_canonical = getattr(value, "to_canonical_dict", None)
    if callable(to_canonical):
        return _canonicalize(to_canonical())
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _safe_setattr(instance: Any, field_name: str, value: Any) -> None:
    try:
        setattr(instance, field_name, value)
    except (AttributeError, TypeError):
        object.__setattr__(instance, field_name, value)


def _is_instance_sealed(instance: Any) -> bool:
    state = getattr(instance, "__dict__", None)
    if isinstance(state, dict):
        return bool(state.get("_fabric_sealed", False))
    return bool(getattr(instance, "_fabric_sealed", False))


def _iter_public_attr_names(instance: Any) -> set[str]:
    names: set[str] = set()

    state = getattr(instance, "__dict__", None)
    if isinstance(state, dict):
        names.update(state.keys())

    for cls in type(instance).__mro__:
        slots = cls.__dict__.get("__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for slot_name in slots:
            if slot_name in {"__dict__", "__weakref__"}:
                continue
            names.add(slot_name)

    if is_dataclass(instance):
        for dataclass_field in fields(instance):
            names.add(dataclass_field.name)

    return names


def _compact_vector_repr(vector: VersionVector | None) -> str:
    if vector is None:
        return "{}"
    parts = [f"{key}:{value}" for key, value in vector.clock if int(value) != 0]
    return "{" + ",".join(parts) + "}"


class FabricSerializerMixin:
    """Canonical serializer mixin for stable hashing and transport."""

    _fabric_excluded_fields: ClassVar[tuple[str, ...]] = ()

    def to_canonical_dict(self) -> dict[str, Any]:
        excluded = set(getattr(type(self), "_fabric_excluded_fields", ()))
        payload: dict[str, Any] = {}
        for field_name in sorted(_iter_public_attr_names(self)):
            if field_name.startswith("_") or field_name in excluded:
                continue
            try:
                value = getattr(self, field_name)
            except AttributeError:
                continue
            payload[field_name] = _canonicalize(value)
        return payload

    def to_msgpack(self) -> bytes:
        payload = self.to_canonical_dict()
        try:
            import msgpack
        except ImportError:
            return json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        return msgpack.packb(payload, use_bin_type=True)

    @classmethod
    def from_msgpack(cls, data: bytes) -> Self:
        try:
            import msgpack
        except ImportError:
            unpacked: Any = json.loads(data.decode("utf-8"))
        else:
            unpacked = msgpack.unpackb(data, raw=False)
        if not isinstance(unpacked, Mapping):
            raise TypeError(f"{cls.__name__}.from_msgpack expected a mapping payload")
        return cls(**dict(unpacked))


class FabricHashMixin(FabricSerializerMixin):
    """Hashing helpers for fabric objects and row dictionaries."""

    def compute_hash(self) -> str:
        payload = json.dumps(
            self.to_canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_dict_hash(payload: Mapping[str, Any]) -> str:
        canonical = _canonicalize(payload)
        if not isinstance(canonical, dict):
            canonical = {"value": canonical}
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


FABRIC_REGISTRY: dict[str, type] = {}

_MUTATING_SENTINEL = "_fabric_mutating"
_MUTATING_WRAPPED = "_fabric_mutating_wrapped"
_INIT_WRAPPED = "_fabric_init_wrapped"


def mutating(fn: Callable[..., Any]) -> Callable[..., Any]:
    setattr(fn, _MUTATING_SENTINEL, True)
    return fn


class FabricObjectMeta(type):
    """Shared metaclass for fabric-aware classes.

    This metaclass is designed to be composable with existing metaclasses.
    If a class already uses another metaclass (for example registration
    metaclasses on existing runtimes), define a combined metaclass at the
    use-site: ``class Combined(FabricObjectMeta, OtherMeta): ...``.
    """

    _NON_REGISTRABLE_NAMES: ClassVar[set[str]] = {
        "FabricSerializerMixin",
        "FabricHashMixin",
        "FabricIdentity",
    }

    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        declared_contract = tuple(namespace.get("_abstract_methods", ()) or ())
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)

        is_abstract = bool(namespace.get("__abstract_fabric__", False))
        if "__abstract_fabric__" not in namespace and any(
            getattr(base, "__abstract_fabric__", False) for base in bases
        ):
            is_abstract = False
            setattr(cls, "__abstract_fabric__", False)

        contract_methods = tuple(getattr(cls, "_abstract_methods", ()) or ())
        inherits_same_contract = bool(contract_methods) and any(
            tuple(getattr(base, "_abstract_methods", ()) or ()) == contract_methods
            for base in bases
        )
        if contract_methods and not is_abstract and (declared_contract or inherits_same_contract):
            missing = [
                method_name
                for method_name in contract_methods
                if not callable(getattr(cls, method_name, None))
            ]
            if missing:
                raise FabricContractError(
                    f"{cls.__module__}.{cls.__qualname__} is missing required "
                    f"fabric methods: {', '.join(sorted(missing))}"
                )

        if not is_abstract and name not in mcls._NON_REGISTRABLE_NAMES:
            registry_key = f"{cls.__module__}.{cls.__qualname__}"
            if registry_key in FABRIC_REGISTRY:
                logger.debug("Fabric registry key already present; skipping: %s", registry_key)
            else:
                FABRIC_REGISTRY[registry_key] = cls

        cls.__init__ = mcls._wrap_init(cls.__init__)  # type: ignore[method-assign]

        for attr_name, attr_value in namespace.items():
            wrapped = mcls._wrap_mutating_attr(cls, attr_name, attr_value)
            if wrapped is not None:
                setattr(cls, attr_name, wrapped)

        if "__repr__" not in namespace:

            def __repr__(self: Any) -> str:
                fabric_uuid = getattr(self, "fabric_uuid", None)
                if isinstance(fabric_uuid, uuid.UUID):
                    uuid_short = fabric_uuid.hex[:8]
                elif fabric_uuid is None:
                    uuid_short = "none"
                else:
                    uuid_short = str(fabric_uuid)[:8]

                content_hash = str(getattr(self, "content_hash", "none") or "none")
                hash_short = content_hash[:8]

                vector = getattr(self, "version_vector", None)
                if not isinstance(vector, VersionVector):
                    vector = None
                vec_short = _compact_vector_repr(vector)
                return f"{cls.__name__}(uuid={uuid_short}, hash={hash_short}, v={vec_short})"

            setattr(cls, "__repr__", __repr__)

        return cls

    @staticmethod
    def _wrap_init(init_fn: Callable[..., Any]) -> Callable[..., Any]:
        if getattr(init_fn, _INIT_WRAPPED, False):
            return init_fn

        @wraps(init_fn)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> None:
            init_fn(self, *args, **kwargs)
            if _is_instance_sealed(self):
                return
            seal = getattr(self, "_seal", None)
            if callable(seal):
                seal()

        setattr(wrapped, _INIT_WRAPPED, True)
        return wrapped

    @classmethod
    def _wrap_mutating_attr(
        mcls,
        cls: type,
        attr_name: str,
        attr_value: Any,
    ) -> Any | None:
        descriptor_kind: type[staticmethod] | type[classmethod] | None = None
        raw_callable = attr_value

        if isinstance(attr_value, staticmethod):
            descriptor_kind = staticmethod
            raw_callable = attr_value.__func__
        elif isinstance(attr_value, classmethod):
            descriptor_kind = classmethod
            raw_callable = attr_value.__func__

        if not callable(raw_callable) or not getattr(raw_callable, _MUTATING_SENTINEL, False):
            return None
        if getattr(raw_callable, _MUTATING_WRAPPED, False):
            return attr_value
        if descriptor_kind is classmethod:
            logger.debug(
                "Skipping @mutating classmethod %s.%s; mutating methods must be instance methods",
                cls.__qualname__,
                attr_name,
            )
            return attr_value
        if descriptor_kind is staticmethod:
            logger.debug(
                "Skipping @mutating staticmethod %s.%s; mutating methods must be instance methods",
                cls.__qualname__,
                attr_name,
            )
            return attr_value

        @wraps(raw_callable)
        def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            result = raw_callable(self, *args, **kwargs)

            seal = getattr(self, "_seal", None)
            if callable(seal):
                seal()

            existing_vector = getattr(self, "version_vector", VersionVector())
            if isinstance(existing_vector, VersionVector):
                updated_vector = existing_vector.incremented(type(self).__qualname__)
            elif isinstance(existing_vector, Mapping):
                updated_vector = VersionVector(dict(existing_vector)).incremented(
                    type(self).__qualname__
                )
            else:
                updated_vector = VersionVector({type(self).__qualname__: 1})
            _safe_setattr(self, "version_vector", updated_vector)

            compute_hash = getattr(self, "compute_hash", None)
            if callable(compute_hash):
                _safe_setattr(self, "content_hash", compute_hash())

            lineage_refs = getattr(self, "lineage_refs", None)
            if isinstance(lineage_refs, list):
                parent_uuid = getattr(self, "fabric_uuid", None)
                lineage_refs.append(
                    LineageRef(
                        transform_kind="self.mutation",
                        source_table_id=str(parent_uuid) if parent_uuid is not None else None,
                        details={"method": attr_name},
                    )
                )
            return result

        setattr(wrapped, _MUTATING_WRAPPED, True)
        setattr(wrapped, _MUTATING_SENTINEL, True)
        return wrapped


class FabricIdentity(FabricHashMixin, metaclass=FabricObjectMeta):
    """Identity + hash + lineage mixin for fabric entities."""

    __abstract_fabric__ = True
    _fabric_excluded_fields: ClassVar[tuple[str, ...]] = (
        "fabric_uuid",
        "content_hash",
        "created_at",
        "lineage_refs",
        "_fabric_sealed",
    )
    __slots__ = (
        "fabric_uuid",
        "content_hash",
        "version_vector",
        "lineage_refs",
        "created_at",
        "_fabric_sealed",
    )

    fabric_uuid: uuid.UUID
    content_hash: str
    version_vector: VersionVector
    lineage_refs: list[LineageRef]
    created_at: datetime

    def _seal(self) -> None:
        if _is_instance_sealed(self):
            return

        if getattr(self, "fabric_uuid", None) is None:
            _safe_setattr(self, "fabric_uuid", uuid.uuid4())
        if getattr(self, "created_at", None) is None:
            _safe_setattr(self, "created_at", datetime.utcnow())
        if not isinstance(getattr(self, "version_vector", None), VersionVector):
            _safe_setattr(
                self,
                "version_vector",
                VersionVector({type(self).__qualname__: 0}),
            )
        if not isinstance(getattr(self, "lineage_refs", None), list):
            _safe_setattr(self, "lineage_refs", [])

        _safe_setattr(self, "content_hash", self.compute_hash())
        _safe_setattr(self, "_fabric_sealed", True)

    def add_lineage_ref(
        self,
        *,
        transform_kind: str,
        parent_uuid: str | uuid.UUID | None = None,
        **details: Any,
    ) -> None:
        self._seal()
        source_table_id = str(parent_uuid) if parent_uuid is not None else None
        self.lineage_refs.append(
            LineageRef(
                transform_kind=transform_kind,
                source_table_id=source_table_id,
                details=dict(details),
            )
        )


__all__ = [
    "FABRIC_REGISTRY",
    "FabricContractError",
    "FabricHashMixin",
    "FabricIdentity",
    "FabricObjectMeta",
    "FabricSerializerMixin",
    "LineageRef",
    "VersionVector",
    "mutating",
]
