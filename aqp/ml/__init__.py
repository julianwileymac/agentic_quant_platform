"""Compatibility shim for the extracted ``aqp_models`` package.

The machine-learning subsystem was extracted into a top-level
:mod:`aqp_models` boundary package per ``aqp_docs/docs/concepts/platform/repository-split.md``.
This shim aliases every submodule of :mod:`aqp_models` under the legacy
``aqp.ml`` name so existing imports (``from aqp.ml.alpha_backtest_experiment
import AlphaBacktestExperiment`` etc.) keep working through one release
cycle.

New code should import from :mod:`aqp_models` directly.
"""
from __future__ import annotations

import importlib as _importlib
import pkgutil as _pkgutil
import sys as _sys
import warnings as _warnings

import aqp_models as _aqp_models

# Emit a one-time deprecation warning so legacy callers know to migrate.
_warnings.warn(
    "aqp.ml is deprecated; import from aqp_models instead. "
    "The compatibility shim will be removed in a future release.",
    DeprecationWarning,
    stacklevel=2,
)

# Eager-import every submodule of ``aqp_models`` and alias it under
# ``aqp.ml.<name>``. This is what makes
# ``from aqp.ml.models.tree import LGBModel`` resolve via the
# already-imported ``aqp_models.models.tree`` rather than searching the
# (empty) ``aqp/ml/`` package directory.
for _modinfo in _pkgutil.walk_packages(_aqp_models.__path__, prefix="aqp_models."):
    _src_name = _modinfo.name
    # Skip the new ``serving`` subpackage — it doesn't have an
    # ``aqp.ml`` analogue and lives behind ``aqp.llm.{vllm_runner,
    # ollama_client}`` shims instead.
    if _src_name.startswith("aqp_models.serving"):
        continue
    _dst_name = "aqp.ml" + _src_name[len("aqp_models"):]
    try:
        _mod = _importlib.import_module(_src_name)
    except Exception:  # noqa: BLE001 - heavy optional deps may not be installed
        continue
    _sys.modules[_dst_name] = _mod

# Re-export the public top-level surface so ``from aqp.ml import DatasetH``
# still works for callers that don't reach into a submodule.
from aqp_models import *  # noqa: F401,F403,E402

# Mirror ``__all__`` so ``from aqp.ml import *`` matches the new package.
try:
    from aqp_models import __all__ as _aqp_models__all__  # noqa: E402
    __all__ = list(_aqp_models__all__)
except ImportError:  # pragma: no cover
    __all__ = []
