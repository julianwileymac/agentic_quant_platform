"""OpenBB-parity ``Fetcher[Q, R]`` + ``QueryParams`` + ``Data`` abstractions.

Port of the three core classes from OpenBB's
``openbb_platform/core/openbb_core/provider/abstract/`` with AQP-specific
extensions:

- ``cost_tier`` — ``free | paid | premium`` (unlocks filtering by the "only
  free providers" policy in the UI).
- ``vendor_key`` — ties a fetcher to a row in the ``data_sources`` table so
  credential + rate-limit metadata can be resolved at runtime.
- ``rate_limit_key`` — used by the async orchestrator to throttle concurrent
  requests per vendor.
- Sync-friendly ``fetch`` that does not require an event loop (wrapping the
  async path via :func:`aqp.providers.utils.run_sync`).

Every standard_model in :mod:`aqp.providers.standard_models` extends
:class:`QueryParams` and :class:`Data` from here, so providers can inherit
the schemas and get canonical field names for free.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import (
    Any,
    Generic,
    TypeVar,
    get_args,
    get_origin,
)

from pydantic import (
    AliasGenerator,
    BaseModel,
    ConfigDict,
    alias_generators,
    model_validator,
)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CostTier(StrEnum):
    """Monetization tier for a provider fetcher."""

    NONE = "none"
    FREE = "free"
    FREEMIUM = "freemium"
    PAID = "paid"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


# ---------------------------------------------------------------------------
# QueryParams base
# ---------------------------------------------------------------------------


class QueryParams(BaseModel):
    """Base class for typed query parameters.

    Mirrors OpenBB's ``QueryParams``:

    - ``__alias_dict__`` maps canonical names → provider-native names for
      the specific provider that a subclass targets (FMP calls it ``cik``,
      Intrinio calls it ``identifier``, …).
    - ``__json_schema_extra__`` carries provider-specific JSON schema extras
      that surface in the REST API schema.

    ``extra="allow"`` keeps us forward-compatible with new provider params
    without needing a schema bump every time.
    """

    __alias_dict__: dict[str, str] = {}
    __json_schema_extra__: dict[str, Any] = {}

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"{', '.join(f'{k}={v}' for k, v in self.model_dump().items())})"
        )

    def model_dump(self, *args, **kwargs):  # type: ignore[override]
        original = super().model_dump(*args, **kwargs)
        if self.__alias_dict__:
            return {self.__alias_dict__.get(k, k): v for k, v in original.items()}
        return original


# ---------------------------------------------------------------------------
# Data base
# ---------------------------------------------------------------------------


class Data(BaseModel):
    """Base class for every standard_model Data payload.

    Mirrors OpenBB's ``Data``:

    - ``extra="allow"`` keeps provider-specific columns on the object.
    - Validation aliases use ``to_camel`` so upstream JSON APIs that use
      camelCase (most do) deserialise cleanly; serialization aliases use
      ``to_snake`` so the Python side stays idiomatic.
    """

    __alias_dict__: dict[str, str] = {}

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        strict=False,
        alias_generator=AliasGenerator(
            validation_alias=alias_generators.to_camel,
            serialization_alias=alias_generators.to_snake,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"{', '.join(f'{k}={v}' for k, v in super().model_dump().items())})"
        )

    @model_validator(mode="before")
    @classmethod
    def _use_alias(cls, values):
        aliases = {orig: alias for alias, orig in cls.__alias_dict__.items()}
        if aliases and isinstance(values, dict):
            return {aliases.get(k, k): v for k, v in values.items()}
        return values


# ---------------------------------------------------------------------------
# AnnotatedResult
# ---------------------------------------------------------------------------


@dataclass
class AnnotatedResult(Generic[TypeVar("R")]):
    """Wrapper returned by a :class:`Fetcher` when metadata accompanies results.

    Mirrors OpenBB's ``AnnotatedResult``: the concrete ``result`` (usually a
    list of ``Data``) is paired with a ``metadata`` dict holding query-level
    info (``next_page_token``, ``rate_limit_remaining``, ``retrieved_at``…).
    """

    result: Any
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


Q = TypeVar("Q", bound=QueryParams)
R = TypeVar("R")


class _ClassProperty:
    """Minimal ``classproperty`` shim (OpenBB ships its own)."""

    def __init__(self, fn):
        self.fn = fn

    def __get__(self, obj, owner):
        return self.fn(owner)


class Fetcher(Generic[Q, R]):
    """Abstract fetcher contract.

    Concrete providers subclass with::

        class FmpBalanceSheetFetcher(Fetcher[BalanceSheetQueryParams, list[BalanceSheetData]]):
            vendor_key = "fmp"
            cost_tier = CostTier.FREEMIUM

            @staticmethod
            def transform_query(params: dict[str, Any]) -> BalanceSheetQueryParams:
                ...

            @staticmethod
            async def aextract_data(query, credentials):
                ...

            @staticmethod
            def transform_data(query, data, **kwargs) -> list[BalanceSheetData]:
                ...
    """

    require_credentials: bool = True
    vendor_key: str = "unknown"
    rate_limit_key: str | None = None
    cost_tier: CostTier = CostTier.NONE
    description: str = ""

    # ---- lifecycle ------------------------------------------------------

    @staticmethod
    def transform_query(params: dict[str, Any]) -> Q:  # type: ignore[type-var]
        """Turn a raw ``dict`` into the typed query object."""
        raise NotImplementedError

    @staticmethod
    async def aextract_data(query: Q, credentials: dict[str, str] | None) -> Any:  # type: ignore[type-var]
        """Async path: fetch the raw provider payload."""

    @staticmethod
    def extract_data(query: Q, credentials: dict[str, str] | None) -> Any:  # type: ignore[type-var]
        """Sync path: fetch the raw provider payload."""

    @staticmethod
    def transform_data(query: Q, data: Any, **kwargs) -> R | AnnotatedResult[R]:  # type: ignore[type-var]
        """Validate + reshape the raw payload into the typed ``Data`` return."""
        raise NotImplementedError

    def __init_subclass__(cls, *args, **kwargs) -> None:
        super().__init_subclass__(*args, **kwargs)
        # If the subclass implements the async variant, route sync calls to it.
        if cls.aextract_data != Fetcher.aextract_data:
            cls.extract_data = cls.aextract_data  # type: ignore[method-assign]

    # ---- dispatch -------------------------------------------------------

    @classmethod
    async def fetch_data(
        cls,
        params: dict[str, Any],
        credentials: dict[str, str] | None = None,
        **kwargs,
    ) -> R | AnnotatedResult[R]:
        query = cls.transform_query(params=params)
        data = cls.extract_data(query=query, credentials=credentials, **kwargs)
        if asyncio.iscoroutine(data):
            data = await data
        return cls.transform_data(query=query, data=data, **kwargs)

    @classmethod
    def fetch(
        cls,
        params: dict[str, Any],
        credentials: dict[str, str] | None = None,
        **kwargs,
    ) -> R | AnnotatedResult[R]:
        """Synchronous entry point that transparently handles async providers."""
        query = cls.transform_query(params=params)
        data = cls.extract_data(query=query, credentials=credentials, **kwargs)
        if asyncio.iscoroutine(data):
            data = asyncio.get_event_loop().run_until_complete(data)
        return cls.transform_data(query=query, data=data, **kwargs)

    # ---- introspection --------------------------------------------------

    @_ClassProperty
    def query_params_type(cls):  # type: ignore[no-self-argument]
        return cls.__orig_bases__[0].__args__[0]  # type: ignore[attr-defined]

    @_ClassProperty
    def return_type(cls):  # type: ignore[no-self-argument]
        rt = cls.__orig_bases__[0].__args__[1]  # type: ignore[attr-defined]
        if get_origin(rt) is AnnotatedResult:
            rt = get_args(rt)[0]
        return rt

    @_ClassProperty
    def data_type(cls):  # type: ignore[no-self-argument]
        rt = cls.__orig_bases__[0].__args__[1]  # type: ignore[attr-defined]
        return _unwrap_list(rt)

    @classmethod
    def describe(cls) -> dict[str, Any]:
        """Return a JSON-serialisable summary used by the UI catalog."""
        return {
            "fetcher": f"{cls.__module__}.{cls.__qualname__}",
            "vendor_key": cls.vendor_key,
            "rate_limit_key": cls.rate_limit_key or cls.vendor_key,
            "cost_tier": cls.cost_tier.value,
            "require_credentials": cls.require_credentials,
            "description": cls.description,
        }


def _unwrap_list(tp: Any) -> Any:
    """If ``tp`` is ``list[X]`` / ``List[X]``, return ``X``; else ``tp``."""
    origin = get_origin(tp)
    if origin is list:
        return get_args(tp)[0]
    return tp
