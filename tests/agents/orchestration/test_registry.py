"""Phase 1 tests for the OrchestrationAdapter metaclass + registry.

Covers:

- :class:`OrchestrationAdapterMeta` auto-registers concrete subclasses
  under :func:`aqp.core.registry.register` with the
  ``orchestration_adapter`` kind and a ``subkind:<kind>`` tag.
- Abstract bases (``__abstract_adapter__ = True`` or names starting
  with ``Base``/``_``) are skipped.
- The shadow index in :mod:`aqp.agents.orchestration.registry` exposes
  ``list_adapters("graph")`` / ``get_adapter("alias")`` correctly.
- Unknown adapter kinds raise ``KeyError`` so the studio cannot drift
  past :data:`ADAPTER_KINDS`.
- :data:`ADAPTER_KINDS` matches the documented seven sub-kinds.
"""
from __future__ import annotations

import pytest

from aqp.agents.orchestration import (
    ADAPTER_KINDS,
    AdapterContext,
    AdapterResult,
    OrchestrationAdapter,
    get_adapter,
    list_adapter_aliases,
    list_adapters,
)
from aqp.agents.orchestration.base import ORCHESTRATION_REGISTRY_KIND


def test_adapter_kinds_match_documented_seven():
    """The seven canonical sub-kinds are fixed; bump
    ADAPTER_KINDS_VERSION before changing this list.
    """
    expected = ("graph", "crew", "debate", "fusion", "execution", "schedule", "studio")
    assert ADAPTER_KINDS == expected


def test_metaclass_skips_abstract_bases():
    """Subclasses declaring ``__abstract_adapter__ = True`` aren't
    registered, mirroring :class:`RLComponentMeta`.
    """

    class _BaseTestAdapter(OrchestrationAdapter):
        __abstract_adapter__ = True
        adapter_kind = "graph"

        def invoke(self, state, context):  # pragma: no cover - never called
            return AdapterResult(state=state)

    aliases = list_adapter_aliases("graph")
    assert "_BaseTestAdapter" not in aliases


def test_metaclass_skips_underscore_and_base_prefix_names():
    """Names starting with ``Base`` / ``_`` are skipped."""

    class BaseSkipAdapter(OrchestrationAdapter):
        adapter_kind = "graph"

        def invoke(self, state, context):  # pragma: no cover
            return AdapterResult(state=state)

    class _PrivateAdapter(OrchestrationAdapter):
        adapter_kind = "graph"

        def invoke(self, state, context):  # pragma: no cover
            return AdapterResult(state=state)

    aliases = list_adapter_aliases("graph")
    assert "BaseSkipAdapter" not in aliases
    assert "_PrivateAdapter" not in aliases


def test_concrete_adapter_auto_registers_in_shadow_index():
    """A concrete subclass appears in :func:`list_adapters` immediately."""

    class FakeGraphAdapter(OrchestrationAdapter):
        adapter_kind = "graph"
        adapter_alias = "test_fake_graph"
        adapter_tags = ("test",)
        adapter_source = "aqp"
        adapter_category = "unit_test"

        def invoke(self, state, context):
            return AdapterResult(state=state, status="completed")

    assert "test_fake_graph" in list_adapter_aliases("graph")
    assert get_adapter("test_fake_graph") is FakeGraphAdapter


def test_concrete_adapter_registers_in_global_registry_under_orchestration_kind():
    """The same class is browsable through
    :func:`aqp.core.registry.list_by_kind`.
    """
    from aqp.core.registry import list_by_kind

    class AnotherGraphAdapter(OrchestrationAdapter):
        adapter_kind = "graph"
        adapter_alias = "test_another_graph"

        def invoke(self, state, context):
            return AdapterResult(state=state)

    by_kind = list_by_kind(ORCHESTRATION_REGISTRY_KIND)
    assert "test_another_graph" in by_kind
    assert by_kind["test_another_graph"] is AnotherGraphAdapter


def test_register_is_called_exactly_once_per_concrete_class():
    """Defining the same alias twice replaces the entry (last-wins),
    same semantics as :func:`aqp.core.registry.register`.
    """

    class FirstAdapter(OrchestrationAdapter):
        adapter_kind = "crew"
        adapter_alias = "dupe_alias"

        def invoke(self, state, context):
            return AdapterResult(state=state)

    first_class = get_adapter("dupe_alias")

    class SecondAdapter(OrchestrationAdapter):
        adapter_kind = "crew"
        adapter_alias = "dupe_alias"

        def invoke(self, state, context):
            return AdapterResult(state=state)

    second_class = get_adapter("dupe_alias")
    assert first_class is FirstAdapter
    assert second_class is SecondAdapter
    assert first_class is not second_class


def test_list_adapters_with_unknown_kind_raises():
    with pytest.raises(KeyError):
        list_adapters("not_a_real_kind")


def test_get_adapter_unknown_alias_raises():
    with pytest.raises(KeyError):
        get_adapter("definitely_not_registered_xyz")


def test_describe_emits_doc_first_line():
    """The studio uses :meth:`OrchestrationAdapter.describe` to render
    the dropdown — assert it produces a JSON-friendly shape with the
    expected keys.
    """

    class DescribeMeAdapter(OrchestrationAdapter):
        """First-line summary used by the studio dropdown.

        Longer rationale appears below the fold.
        """

        adapter_kind = "studio"
        adapter_alias = "describe_me"
        adapter_tags = ("ui",)
        adapter_source = "aqp"
        adapter_category = "studio"

        def invoke(self, state, context):
            return AdapterResult(state=state)

    desc = DescribeMeAdapter.describe()
    assert desc["alias"] == "describe_me"
    assert desc["kind"] == "studio"
    assert desc["source"] == "aqp"
    assert desc["category"] == "studio"
    assert "ui" in desc["tags"]
    assert desc["doc"].startswith("First-line summary")


def test_orchestration_kind_decorator_present_on_core_registry():
    """Plan asks for an explicit kind decorator on aqp.core.registry."""
    from aqp.core import registry as core_registry

    assert hasattr(core_registry, "orchestration_adapter")
    assert callable(core_registry.orchestration_adapter)


def test_adapter_context_halt_check_is_noop_when_unwired():
    """``AdapterContext.is_halted()`` returns ``False`` when no checker
    is attached, so adapters can always poll it safely.
    """
    ctx = AdapterContext(
        workflow_run_id="rid",
        workflow_spec_name="spec",
        request_id="req",
    )
    assert ctx.is_halted() is False
