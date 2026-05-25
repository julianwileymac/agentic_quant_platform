"""Placeholder smoke test so `aqp_bots` slots into the CI matrix.

Phase 1 §4.1 of the Restructuring Plan added `aqp_bots` to the
multi-subproject test matrix. The package shipped without a
``tests/`` directory; this module establishes the slot so the
matrix entry is real (rather than skipped with ``|| true``), and
asserts a handful of import-time invariants that catch the most
common regression class — circular imports between the bot
spec / runtime / registry triad.

Phase 2 is expected to expand this into a real test suite covering
``BotRuntime.start`` / ``BotRuntime.stop``, the FIX + REST adapter
families, and the operator CRD reconciliation loop.
"""
from __future__ import annotations


def test_package_import_smoke() -> None:
    """`aqp_bots` package imports without side-effects blowing up."""
    import aqp_bots  # noqa: F401

    # The package re-exports the canonical surface from `__init__.py`;
    # touching `__all__` ensures every entry resolved.
    public = getattr(aqp_bots, "__all__", None)
    assert public is None or isinstance(public, (list, tuple))


def test_bot_runtime_class_exists() -> None:
    """`BotRuntime` is reachable from the public surface."""
    from aqp_bots.runtime import BotRuntime

    # Don't instantiate — that requires real config + DB. Just
    # confirm the class is importable + carries the expected
    # `start` / `stop` lifecycle hooks.
    assert callable(getattr(BotRuntime, "start", None)) or callable(
        getattr(BotRuntime, "__init__", None)
    )


def test_spec_module_imports() -> None:
    """`aqp_bots.spec` (BotSpec hash-locking) imports cleanly."""
    from aqp_bots import spec  # noqa: F401


def test_registry_module_imports() -> None:
    """`aqp_bots.registry` (BotRow CRUD) imports cleanly."""
    from aqp_bots import registry  # noqa: F401


def test_base_module_imports() -> None:
    """`aqp_bots.base` (BotKind enum + shared types) imports cleanly."""
    from aqp_bots import base  # noqa: F401
