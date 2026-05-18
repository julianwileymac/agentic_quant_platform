"""Regression test for defect 5: dataset_loading_agent route import drift.

The route used to import ``get_spec`` from ``aqp.agents.registry`` —
but the registry only exports :func:`aqp.agents.registry.get_agent_spec`.
The fix swaps the import so the route is reachable again.
"""
from __future__ import annotations


def test_dataset_loading_agent_module_imports():
    """``aqp.api.routes.dataset_loading_agent`` must import cleanly."""
    import importlib

    mod = importlib.import_module("aqp.api.routes.dataset_loading_agent")
    assert hasattr(mod, "router")
    assert hasattr(mod, "consult")


def test_dataset_loading_agent_uses_correct_registry_symbol():
    """Source must import ``get_agent_spec``, not the legacy ``get_spec``."""
    import inspect

    from aqp.api.routes import dataset_loading_agent as mod

    source = inspect.getsource(mod.consult)
    assert "get_agent_spec" in source
    assert "import get_spec" not in source
    assert "get_spec(" not in source
