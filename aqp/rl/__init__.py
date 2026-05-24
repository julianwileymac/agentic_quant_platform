"""Compatibility shim for the extracted ``aqp_rl`` package.

The reinforcement-learning subsystem was extracted into a top-level
:mod:`aqp_rl` boundary package per ``aqp_docs/repository-split.md``.
This shim aliases every submodule of :mod:`aqp_rl` under the legacy
``aqp.rl`` name so existing imports (``from aqp.rl.runtime import
RLRuntime`` etc.) keep working through one release cycle.

New code should import from :mod:`aqp_rl` directly.
"""
from __future__ import annotations

import importlib as _importlib
import pkgutil as _pkgutil
import sys as _sys
import warnings as _warnings

import aqp_rl as _aqp_rl

# Emit a one-time deprecation warning so legacy callers know to migrate.
_warnings.warn(
    "aqp.rl is deprecated; import from aqp_rl instead. "
    "The compatibility shim will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

# Eager-import every submodule of ``aqp_rl`` and alias it under
# ``aqp.rl.<name>``. This is what makes
# ``from aqp.rl.core.base import RLComponent`` resolve via the
# already-imported ``aqp_rl.core.base`` rather than searching the
# (empty) ``aqp/rl/`` package directory.
for _modinfo in _pkgutil.walk_packages(_aqp_rl.__path__, prefix="aqp_rl."):
    _src_name = _modinfo.name
    _dst_name = "aqp.rl" + _src_name[len("aqp_rl"):]
    try:
        _mod = _importlib.import_module(_src_name)
    except Exception:  # noqa: BLE001 - heavy optional deps may not be installed
        continue
    _sys.modules[_dst_name] = _mod

# Re-export the public top-level surface so ``from aqp.rl import RLRuntime``
# still works for callers that don't reach into a submodule.
from aqp_rl import *  # noqa: F401,F403,E402

# Mirror ``__all__`` so ``from aqp.rl import *`` matches the new package.
try:
    from aqp_rl import __all__ as _aqp_rl__all__  # noqa: E402
    __all__ = list(_aqp_rl__all__)
except ImportError:  # pragma: no cover
    __all__ = []
