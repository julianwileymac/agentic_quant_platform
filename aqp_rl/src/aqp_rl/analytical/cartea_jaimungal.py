"""Thin re-export of :mod:`aqp.optimal_control.cartea_jaimungal`.

AQP's monolith ships the Cartea-Jaimungal-Penalva HJB solver at
:mod:`aqp.optimal_control.cartea_jaimungal`. This module re-exports
the same symbols under :mod:`aqp_rl.analytical.cartea_jaimungal`
so RL code can stay inside the ``aqp_rl`` package boundary.

Importing the monolith module is unconditional — when it's missing
the import will fail at module-load time. The :mod:`aqp_rl.analytical`
package's ``__init__`` guards against this with a ``try/except`` so
``aqp_rl.analytical`` stays importable without the monolith.
"""
from __future__ import annotations

from aqp.optimal_control.cartea_jaimungal import (  # noqa: F401
    CarteaJaimungalParams,
)

# The trading-rate function is available under multiple names across
# AQP's history; try the canonical one first.
try:
    from aqp.optimal_control.cartea_jaimungal import optimal_trading_rate  # noqa: F401
except ImportError:
    try:
        from aqp.optimal_control.cartea_jaimungal import solve as optimal_trading_rate  # noqa: F401
    except ImportError:
        optimal_trading_rate = None  # type: ignore[assignment]

try:
    from aqp.optimal_control.cartea_jaimungal import (  # noqa: F401
        optimal_liquidation_value,
    )
except ImportError:
    optimal_liquidation_value = None  # type: ignore[assignment]


__all__ = [
    "CarteaJaimungalParams",
    "optimal_liquidation_value",
    "optimal_trading_rate",
]
