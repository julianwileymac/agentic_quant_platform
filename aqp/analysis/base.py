"""Core abstractions shared by every analysis flow.

The umbrella keeps three primitives small + explicit:

- :class:`FlowParams` — Pydantic base for per-flow parameter models;
  subclasses give us free JSON-Schema generation for the UI builder.
- :class:`FlowResult` — JSON-serialisable per-flow output. ``rows`` is
  a small preview; ``arrow_table`` is the optional bulk payload that
  the runtime persists to Iceberg under
  ``aqp_gold_analysis_<namespace>``; ``chart`` is a Plotly-friendly
  JSON dict the lab can render directly.
- :class:`AnalysisFlow` (Protocol) + :class:`FlowDescriptor` — the
  registered shape of a flow.

Flows are registered via the
:func:`aqp.analysis.registry.register_analysis_flow` decorator. The
function-style design mirrors :mod:`aqp.ml.flows` so the migration is
surface-only — heavy lifting still happens in `numpy` / `pandas` /
`statsmodels` / `scipy` / `sklearn` / `arch`.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

logger = logging.getLogger(__name__)


class FlowParams(BaseModel):
    """Base for per-flow Pydantic param models.

    Concrete flows subclass this and add fields. The class doubles as
    the JSON-schema source for the lab's auto-generated forms — that's
    why we forbid extras (``extra="forbid"``) so unknown fields raise
    in tests instead of silently being dropped.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class FlowSchema(BaseModel):
    """JSON-friendly schema record served by ``GET /analysis/flows``."""

    name: str
    namespace: str
    label: str
    description: str
    tags: list[str] = Field(default_factory=list)
    params_schema: dict[str, Any] = Field(default_factory=dict)
    requires_dataset: bool = True
    output_kind: str = "table"  # table | metrics | chart | mixed
    optional_dependencies: list[str] = Field(default_factory=list)


class FlowResult(BaseModel):
    """Outcome of a single :class:`AnalysisFlow.run`.

    ``rows`` is a small preview suitable for direct JSON serialisation
    (capped at ~500 rows by convention). The bulk payload, if any,
    travels in ``arrow_table`` (a :class:`pyarrow.Table`) and is
    persisted to Iceberg by :class:`aqp.analysis.runtime.AnalysisRuntime`
    when the flow is part of a saved spec.

    ``chart`` is a Plotly figure-dict (``{data: [...], layout: {...}}``)
    so the lab can render it without an extra round-trip.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    flow: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    chart: dict[str, Any] | None = None
    error: str | None = None

    # Internal — never exposed via the public REST schema, but
    # consumed by the runtime to write a per-step Iceberg table.
    arrow_table: Any | None = Field(default=None, exclude=True, repr=False)
    iceberg_identifier: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Round-trip via Pydantic to drop the Arrow blob."""
        return self.model_dump(mode="json", exclude={"arrow_table"})


@dataclass(slots=True, frozen=True)
class FlowContext:
    """Per-call context handed to a flow.

    The runtime fills ``run_id`` / ``task_id`` / ``request_context`` so
    flows can attribute Iceberg writes and progress emits without the
    flow body needing to know about Celery, MLflow, or tenancy.
    """

    dataset_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    request_context: Any | None = None
    upstream: dict[str, FlowResult] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AnalysisFlow(Protocol):
    """Runtime-checkable shape of a registered flow callable.

    Concrete flows are plain functions; the Protocol only exists so
    type-checkers can talk about them.
    """

    def __call__(  # pragma: no cover - typing only
        self,
        df: Any,
        params: FlowParams,
        ctx: FlowContext,
    ) -> FlowResult:
        ...


# Match the runner signature used by every concrete flow.
FlowRunner = Callable[[Any, FlowParams, FlowContext], FlowResult]


@dataclass(slots=True, frozen=True)
class FlowDescriptor:
    """Metadata-rich record kept in the flow registry.

    The descriptor is the single source of truth used by:

    - the REST/UI layer (``GET /analysis/flows``) to list flows + build
      forms;
    - :class:`aqp.analysis.runtime.AnalysisRuntime` to dispatch a step;
    - :func:`persist_spec` to validate that every step references a
      flow we actually know how to execute.
    """

    name: str
    namespace: str
    label: str
    description: str
    runner: FlowRunner
    params_model: type[FlowParams]
    tags: tuple[str, ...] = ()
    requires_dataset: bool = True
    output_kind: str = "table"
    optional_dependencies: tuple[str, ...] = ()
    output_namespace: str | None = None  # default: aqp_gold_analysis_<namespace>

    def schema(self) -> FlowSchema:
        return FlowSchema(
            name=self.name,
            namespace=self.namespace,
            label=self.label,
            description=self.description,
            tags=list(self.tags),
            params_schema=self.params_model.model_json_schema(),
            requires_dataset=self.requires_dataset,
            output_kind=self.output_kind,
            optional_dependencies=list(self.optional_dependencies),
        )

    def iceberg_namespace(self) -> str:
        """Default Iceberg namespace for this flow's gold-tier output.

        Convention: ``aqp_gold_analysis_<flow.namespace>``. Concrete
        flows can override by setting :attr:`output_namespace` at
        registration time.
        """
        if self.output_namespace:
            return self.output_namespace
        return f"aqp_gold_analysis_{self.namespace}"


def coerce_arrow(
    rows: list[dict[str, Any]] | None = None,
    *,
    columns: list[str] | None = None,
) -> "pa.Table | None":
    """Best-effort ``rows -> pyarrow.Table`` for flow authors.

    Returns ``None`` when pyarrow is not installed or the rows are
    empty so the runtime treats it as a no-op write. Centralising the
    conversion keeps every flow's Iceberg-sink path uniform.
    """
    if not rows:
        return None
    try:
        import pyarrow as pa  # noqa: F401

        if columns:
            return pa.Table.from_pylist(rows, schema=None).select(columns)
        return pa.Table.from_pylist(rows)
    except Exception:  # noqa: BLE001
        logger.debug("coerce_arrow failed", exc_info=True)
        return None


__all__ = [
    "AnalysisFlow",
    "FlowContext",
    "FlowDescriptor",
    "FlowParams",
    "FlowResult",
    "FlowRunner",
    "FlowSchema",
    "coerce_arrow",
]
