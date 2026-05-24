"""Thin re-export of :mod:`aqp.optimal_control.avellaneda_stoikov`.

AQP's monolith ships the JAX-compiled Avellaneda & Stoikov 2008
optimal-quotes computation at
:mod:`aqp.optimal_control.avellaneda_stoikov`. This module re-exports
the same symbols under :mod:`aqp_rl.analytical.avellaneda_stoikov`
so RL code can stay inside the ``aqp_rl`` package boundary when
configuring an :class:`AvellanedaStoikovResidualPolicy`.

The underlying functions
========================

- :func:`compute_optimal_quotes` — JIT-compiled (when JAX is
  installed); takes ``mid_price, inventory, gamma, sigma, k, T_minus_t``
  and returns a result object with ``reservation_price`` and
  ``half_spread``.
- :class:`AvellanedaStoikovParams` — frozen dataclass packaging the
  default ``(γ, σ, k, T_minus_t)`` knobs.
- :func:`glft_closed_form` — the Guéant-Lehalle-Fernandez-Tapia (2013)
  closed-form approximation used in
  :class:`aqp.strategies.hft.alphas.GLFTMM`.

Importing this module raises :class:`ImportError` only when the
monolith's :mod:`aqp.optimal_control` package is itself unavailable
(very rare — would imply a broken AQP install).
"""
from __future__ import annotations

from aqp.optimal_control.avellaneda_stoikov import (  # noqa: F401
    AvellanedaStoikovParams,
    compute_optimal_quotes,
)

try:
    from aqp.optimal_control.avellaneda_stoikov import (  # noqa: F401
        glft_closed_form,
    )
except ImportError:
    glft_closed_form = None  # type: ignore[assignment]


__all__ = [
    "AvellanedaStoikovParams",
    "compute_optimal_quotes",
    "glft_closed_form",
]
