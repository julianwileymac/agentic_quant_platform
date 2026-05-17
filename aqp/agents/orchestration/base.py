"""``OrchestrationAdapter`` ABC + auto-registering metaclass.

Mirrors the canonical
:class:`aqp.rl.core.base.RLComponentMeta` pattern (see
[aqp/rl/core/base.py](../../rl/core/base.py)) so every concrete adapter
self-registers at class-definition time. Subclasses opt in by
declaring two class-level attributes:

- ``adapter_kind``: one of :data:`aqp.agents.orchestration.registry.
  ADAPTER_KINDS` (``graph`` / ``crew`` / ``debate`` / ``fusion`` /
  ``execution`` / ``schedule`` / ``studio``).
- ``adapter_alias``: short stable id used in ``WorkflowSpec.adapter``
  and the Phase 5 studio dropdown. Defaults to the class name.

Optional attributes for the faceted catalog:

- ``adapter_tags`` (tuple[str, ...]).
- ``adapter_source`` (str, the inspiration repo this asset was
  extracted from).
- ``adapter_category`` (str, a subtype tag for the UI browser).

Abstract bases — names starting with ``Base``/``_`` or classes that
set ``__abstract_adapter__ = True`` — are intentionally skipped so
only concrete adapter implementations land in the registry.

The metaclass keeps the contract narrow: it never instantiates the
class, never imports a heavy dep, and never crashes module import if
``aqp.core.registry.register`` raises (the failure is logged and
discovery falls back to the per-kind shadow registry maintained
locally — see :mod:`aqp.agents.orchestration.registry`).
"""
from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod
from typing import Any, ClassVar

from aqp.core.registry import register

logger = logging.getLogger(__name__)


ORCHESTRATION_REGISTRY_KIND = "orchestration_adapter"
"""Top-level component-kind used in :mod:`aqp.core.registry`.

The per-sub-kind index lives in
:mod:`aqp.agents.orchestration.registry`. We register a single
``orchestration_adapter`` kind here so the existing
``list_by_kind`` API on the global registry returns every adapter
in one call; the sub-kind (``graph``/``crew``/...) is exposed as a
tag in the form ``subkind:<kind>``.
"""


class OrchestrationAdapterMeta(ABCMeta):
    """Auto-register concrete :class:`OrchestrationAdapter` subclasses.

    The metaclass:

    1. Skips abstract bases (``__abstract_adapter__ = True``) and
       classes whose name starts with ``Base`` / ``_``.
    2. Resolves ``adapter_alias`` (defaults to ``cls.__name__``) and
       ``adapter_kind`` (inherited from the closest ancestor).
    3. Calls :func:`aqp.core.registry.register` with
       ``kind="orchestration_adapter"`` + ``tags=("subkind:<kind>",
       ...adapter_tags)`` + ``source``/``category`` so the global
       browser surfaces every adapter without each subclass needing
       to remember to decorate itself.
    4. Updates the per-sub-kind shadow index in
       :mod:`aqp.agents.orchestration.registry` so
       :func:`list_adapters("graph")` works without scanning every
       class in the global registry.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):  # type: ignore[override]
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        if namespace.get("__abstract_adapter__", False):
            return cls
        if name.startswith(("Base", "_")):
            return cls
        adapter_kind = getattr(cls, "adapter_kind", None)
        if not adapter_kind:
            # Implementations that forget to set ``adapter_kind`` stay
            # importable but are silently un-registered.  This matches
            # the RLComponentMeta behaviour.
            return cls
        alias = getattr(cls, "adapter_alias", None) or cls.__name__
        tags = tuple(getattr(cls, "adapter_tags", ()) or ())
        source = getattr(cls, "adapter_source", None)
        category = getattr(cls, "adapter_category", None)

        full_tags = tuple({f"subkind:{adapter_kind}", *tags})

        try:
            register(
                name=alias,
                kind=ORCHESTRATION_REGISTRY_KIND,
                tags=full_tags,
                source=source,
                category=category,
            )(cls)
        except Exception:  # noqa: BLE001 - never break the import chain
            logger.debug(
                "OrchestrationAdapter auto-registration failed for %s",
                name,
                exc_info=True,
            )

        # Shadow index (per sub-kind, alias -> class) so the public
        # API in ``aqp.agents.orchestration.registry`` can answer
        # ``list_adapters("graph")`` in O(1) without scanning tags.
        try:
            from aqp.agents.orchestration.registry import _record_adapter

            _record_adapter(adapter_kind, alias, cls)
        except Exception:  # noqa: BLE001
            logger.debug(
                "OrchestrationAdapter shadow-index update failed for %s",
                name,
                exc_info=True,
            )
        return cls


class OrchestrationAdapter(metaclass=OrchestrationAdapterMeta):
    """Abstract base every adapter subclasses.

    Subclasses set the following class attributes (mirroring
    :class:`aqp.rl.core.base.RLComponent`):

    - ``adapter_kind`` (str): one of the seven canonical kinds in
      :data:`aqp.agents.orchestration.registry.ADAPTER_KINDS`.
    - ``adapter_alias`` (str, optional): short stable id used by
      ``WorkflowSpec``. Defaults to the class name.
    - ``adapter_tags`` (tuple[str, ...], optional): extra tags
      surfaced in the registry filters.
    - ``adapter_source`` (str, optional): inspiration repo this
      asset was extracted from (``"tradingagents"``, ``"valuecell"``,
      ``"langflow"``, ``"finrobot"``, ``"finrl"``, ``"aqp"``).
    - ``adapter_category`` (str, optional): faceted category tag.

    Subclasses MUST implement :meth:`invoke`. The Phase 2
    ``WorkflowRuntime`` calls it with a state mapping and an
    :class:`aqp.agents.orchestration.types.AdapterContext`; the
    adapter returns an
    :class:`aqp.agents.orchestration.types.AdapterResult`.

    Adapters MUST NOT:

    - import ORM models directly (rule 22); reach for DataMCP tools.
    - call ``router_complete`` directly (rule 12); declare the model
      on an ``AgentSpec`` and let :class:`AgentRuntime` drive it.
    - write to Iceberg directly (rule 3); use the catalog wrapper.
    - publish to Redis directly (rule 4); use ``_progress.emit``.
    """

    __abstract_adapter__: ClassVar[bool] = True

    adapter_kind: ClassVar[str | None] = None
    adapter_alias: ClassVar[str | None] = None
    adapter_tags: ClassVar[tuple[str, ...]] = ()
    adapter_source: ClassVar[str | None] = None
    adapter_category: ClassVar[str | None] = None

    @abstractmethod
    def invoke(
        self,
        state: Any,
        context: Any,
    ) -> Any:
        """Execute the adapter once for the surrounding workflow run.

        Parameters
        ----------
        state:
            An :class:`aqp.agents.orchestration.state.OrchestrationState`
            mapping. Adapters typically read named slots and write
            their outputs back to the same mapping before returning
            the result.
        context:
            The per-run :class:`aqp.agents.orchestration.types.AdapterContext`.
            Adapters MUST poll ``context.is_halted()`` between long
            inner steps.

        Returns
        -------
        :class:`aqp.agents.orchestration.types.AdapterResult`
            Adapters wrap their outputs in :class:`AdapterResult` so
            the runtime can aggregate telemetry uniformly.
        """

    @classmethod
    def describe(cls) -> dict[str, Any]:
        """Return a JSON-friendly summary used by the studio dropdown."""
        return {
            "alias": cls.adapter_alias or cls.__name__,
            "kind": cls.adapter_kind,
            "module": cls.__module__,
            "class": cls.__name__,
            "tags": list(cls.adapter_tags or ()),
            "source": cls.adapter_source,
            "category": cls.adapter_category,
            "doc": (cls.__doc__ or "").strip().split("\n", 1)[0],
        }


__all__ = [
    "ORCHESTRATION_REGISTRY_KIND",
    "OrchestrationAdapter",
    "OrchestrationAdapterMeta",
]
