"""Normalization strategy contract + registry.

A :class:`BaseNormalizationStrategy` is a stateless function
``(arrow_table, data_contract) -> NormalizationResult`` that:

1. Coerces column types to the contract's declared type-family
2. Drops / renames provider-specific columns
3. Adds derived columns required by Silver (eg. ``vt_symbol``,
   ``as_of_utc``, ``ingested_at``)
4. Validates the output against the contract and emits a list of
   contract violations + drift events for the lineage observer

Strategies are registered globally by string alias (eg. ``equity``,
``options``, ``regulatory.cfpb``) so the Silver-layer transform node
can dispatch on data-domain without hard-coding the dispatch table.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aqp.data.catalog.active_metadata import (
    DataContract,
    validate_contract_against_schema,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NormalizationResult:
    """Outcome of running a normalization strategy."""

    table: Any
    """The normalized PyArrow table."""

    rows_in: int
    """Row count before normalization."""

    rows_out: int
    """Row count after normalization (drops, deduplication)."""

    rows_dropped: int
    """Rows dropped because they failed validation."""

    contract_violations: list[str] = field(default_factory=list)
    """Human-readable violation strings (eg. missing required column)."""

    drift_columns: list[str] = field(default_factory=list)
    """Columns present in the input but not in the contract."""

    notes: list[str] = field(default_factory=list)
    """Free-form transformation notes (renames, derived columns)."""


class BaseNormalizationStrategy:
    """Abstract Silver-layer normalization strategy.

    Subclasses set :attr:`alias` (string used in the strategy registry
    and in :class:`PipelineManifest` ``transform.normalize`` nodes) and
    implement :meth:`normalize`. The base class provides:

    - :meth:`validate` — schema-level contract validation hook
    - :meth:`detect_drift` — column drift detection
    - :meth:`emit_drift_events` — fires ``schema_drift`` lineage events

    All concrete strategies must remain pure functions of (table,
    contract). Side-effects (Iceberg writes, catalog upserts) live
    above this layer.
    """

    alias: str = ""
    description: str = ""
    handles_domains: tuple[str, ...] = ()

    def normalize(
        self,
        table: Any,
        *,
        contract: DataContract | None = None,
    ) -> NormalizationResult:
        """Coerce ``table`` to the canonical Silver schema for this domain.

        Subclasses override this; the base implementation is a no-op
        that just runs the contract check and returns the unchanged
        table.
        """
        violations = (
            validate_contract_against_schema(contract, getattr(table, "schema", None))
            if contract is not None
            else []
        )
        rows = int(getattr(table, "num_rows", 0) or 0)
        drift = self._detect_drift_columns(table, contract)
        if drift:
            self._emit_drift(self.alias, drift, contract)
        return NormalizationResult(
            table=table,
            rows_in=rows,
            rows_out=rows,
            rows_dropped=0,
            contract_violations=violations,
            drift_columns=drift,
        )

    @staticmethod
    def _detect_drift_columns(
        table: Any, contract: DataContract | None
    ) -> list[str]:
        if contract is None or table is None:
            return []
        try:
            present = set(getattr(table, "schema").names)
        except Exception:  # noqa: BLE001
            return []
        return sorted(present - contract.column_names())

    @staticmethod
    def _emit_drift(
        alias: str, drift_columns: list[str], contract: DataContract | None
    ) -> None:
        if not drift_columns:
            return
        try:
            from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

            get_lineage_bus().emit(
                LineageEvent(
                    transform_kind="schema_drift",
                    target_table_id=None,
                    actor=f"normalize.{alias}",
                    actor_kind="service",
                    service_name="normalization",
                    summary=(
                        f"normalize.{alias} detected {len(drift_columns)} drift "
                        f"columns: {', '.join(drift_columns[:5])}"
                    ),
                    details={
                        "drift_columns": drift_columns,
                        "contract_columns": (
                            sorted(contract.column_names())
                            if contract is not None
                            else []
                        ),
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("schema drift emit failed", exc_info=True)

    @staticmethod
    def safe_rename(table: Any, mapping: dict[str, str]) -> Any:
        """Rename columns when they exist; ignore the rest."""
        try:
            existing = list(getattr(table, "schema").names)
        except Exception:  # noqa: BLE001
            return table
        new_names = [mapping.get(name, name) for name in existing]
        if new_names == existing:
            return table
        return table.rename_columns(new_names)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_STRATEGY_REGISTRY: dict[str, type[BaseNormalizationStrategy]] = {}


def register_normalization_strategy(
    alias: str,
) -> Any:
    """Decorator: register a strategy under ``alias``.

    .. code-block:: python

        @register_normalization_strategy("equity")
        class EquityNormalization(BaseNormalizationStrategy):
            ...
    """
    if not alias:
        raise ValueError("alias must not be empty")

    def _wrap(cls: type[BaseNormalizationStrategy]) -> type[BaseNormalizationStrategy]:
        if not issubclass(cls, BaseNormalizationStrategy):
            raise TypeError(
                f"{cls!r} must subclass BaseNormalizationStrategy"
            )
        cls.alias = alias
        if alias in _STRATEGY_REGISTRY and _STRATEGY_REGISTRY[alias] is not cls:
            logger.debug("Replacing normalization strategy %s", alias)
        _STRATEGY_REGISTRY[alias] = cls
        return cls

    return _wrap


def get_normalization_strategy(alias: str) -> BaseNormalizationStrategy:
    """Instantiate the registered strategy for ``alias``."""
    if alias not in _STRATEGY_REGISTRY:
        raise KeyError(
            f"unknown normalization strategy {alias!r}; "
            f"registered: {sorted(_STRATEGY_REGISTRY)}"
        )
    return _STRATEGY_REGISTRY[alias]()


def list_normalization_strategies() -> list[dict[str, Any]]:
    """Return metadata for every registered strategy."""
    out: list[dict[str, Any]] = []
    for alias, cls in sorted(_STRATEGY_REGISTRY.items()):
        out.append(
            {
                "alias": alias,
                "description": cls.description or (cls.__doc__ or "").strip().splitlines()[0]
                if (cls.description or cls.__doc__)
                else "",
                "handles_domains": list(cls.handles_domains),
                "module": cls.__module__,
                "class_name": cls.__name__,
            }
        )
    return out


__all__ = [
    "BaseNormalizationStrategy",
    "NormalizationResult",
    "get_normalization_strategy",
    "list_normalization_strategies",
    "register_normalization_strategy",
]
