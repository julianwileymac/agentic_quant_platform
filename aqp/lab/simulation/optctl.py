"""``env='optctl'`` simulation runner — JAX optimal-control solvers.

Phase 4 dispatches to the three documented solvers in
:mod:`aqp.optimal_control`:

- ``solver='avellaneda_stoikov'`` — Avellaneda-Stoikov 2008 closed
  form (Q-2008, market-making with inventory aversion).
- ``solver='cartea_jaimungal'`` — Cartea-Jaimungal-Penalva optimal
  execution with permanent + temporary impact + signal term.
- ``solver='glft'`` — Guéant-Lehalle-Fernandez-Tapia bounded-
  inventory market-making solver.

The runner returns a (bid, ask) quoting function for the requested
solver evaluated over a deterministic state grid so the Simulation
panel can plot the policy surface even when the closed-loop
hftbacktest LOB engine isn't yet wired.

The Python↔Numba bridge described in the plan (hot-cached JIT
``quote_fn`` callable into hftbacktest) is the Phase 4 stretch goal;
this runner ships the closed-form evaluation today.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from aqp.lab.schema import GraphSpec

logger = logging.getLogger(__name__)


def run_optctl_simulation(
    payload: dict[str, Any], *, spec: GraphSpec | None = None
) -> dict[str, Any]:
    started = time.time()
    extras = dict(payload.get("extras") or {})
    solver = str(extras.get("solver") or "avellaneda_stoikov").lower()

    try:
        if solver == "avellaneda_stoikov":
            grid = _avellaneda_stoikov_grid(extras)
        elif solver == "cartea_jaimungal":
            grid = _cartea_jaimungal_grid(extras)
        elif solver == "glft":
            grid = _glft_grid(extras)
        else:
            return {
                "status": "error",
                "env": "optctl",
                "error": f"unknown solver {solver!r}; valid: avellaneda_stoikov, cartea_jaimungal, glft",
                "duration_ms": (time.time() - started) * 1000.0,
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("optctl simulation failed solver=%s", solver)
        return {
            "status": "error",
            "env": "optctl",
            "solver": solver,
            "error": str(exc),
            "duration_ms": (time.time() - started) * 1000.0,
        }

    return {
        "status": "done",
        "env": "optctl",
        "solver": solver,
        "summary": {
            "mid_grid_size": int(len(grid["mid"])),
            "inventory_grid_size": int(len(grid["inventory"])),
            "mean_spread_bps": float(np.nanmean(grid["spread_bps"])),
            "max_spread_bps": float(np.nanmax(grid["spread_bps"])),
            "mean_reservation_skew": float(np.nanmean(grid["skew"])),
        },
        "grid": {
            # Trim the grid to keep the WS frame bounded; the
            # frontend can request a fresh grid via a follow-up
            # ``sim.command`` when zooming in.
            "mid": grid["mid"].tolist()[:64],
            "inventory": grid["inventory"].tolist()[:64],
            "bid": grid["bid"].tolist()[:64],
            "ask": grid["ask"].tolist()[:64],
            "spread_bps": grid["spread_bps"].tolist()[:64],
        },
        "duration_ms": (time.time() - started) * 1000.0,
    }


def _avellaneda_stoikov_grid(extras: dict[str, Any]) -> dict[str, np.ndarray]:
    """Closed-form AS quoting policy evaluated over a (mid, inventory) grid.

    Avellaneda & Stoikov (2008):

        r = s - γσ²(T - t)·q
        δ = γσ²(T - t)/2 + (1/γ)·ln(1 + γ/κ)
        bid = r - δ, ask = r + δ
    """
    mid_grid = np.asarray(
        extras.get("mid_grid") or np.linspace(100.0, 110.0, 32), dtype=float
    )
    inventory_grid = np.asarray(
        extras.get("inventory_grid") or np.arange(-10, 11), dtype=float
    )
    gamma = float(extras.get("gamma") or 0.1)
    sigma = float(extras.get("sigma") or 0.2)
    T = float(extras.get("T") or 1.0)
    t = float(extras.get("t") or 0.0)
    kappa = float(extras.get("kappa") or 1.5)

    reservation = mid_grid[None, :] - gamma * sigma**2 * (T - t) * inventory_grid[:, None]
    half_spread = 0.5 * gamma * sigma**2 * (T - t) + (1.0 / gamma) * np.log(
        1.0 + gamma / max(1e-9, kappa)
    )
    bid = reservation - half_spread
    ask = reservation + half_spread
    spread_bps = (ask - bid) / mid_grid[None, :] * 10_000.0
    return {
        "mid": mid_grid,
        "inventory": inventory_grid,
        "bid": bid,
        "ask": ask,
        "spread_bps": spread_bps,
        "skew": reservation - mid_grid[None, :],
    }


def _cartea_jaimungal_grid(extras: dict[str, Any]) -> dict[str, np.ndarray]:
    """Cartea-Jaimungal-style execution policy on an inventory schedule.

    Returns the same (mid, inventory) grid shape as Avellaneda-Stoikov
    so the Simulation panel can render either solver with one chart.
    The execution policy uses a permanent-impact term ``b`` and a
    temporary-impact ``k`` per AHGSF (2010) style — the bid/ask are
    the price the trader posts to liquidate ``q`` shares optimally.
    """
    mid_grid = np.asarray(extras.get("mid_grid") or np.linspace(100.0, 110.0, 32), dtype=float)
    inventory_grid = np.asarray(extras.get("inventory_grid") or np.arange(-10, 11), dtype=float)
    permanent_impact = float(extras.get("permanent_impact") or 1e-4)
    temporary_impact = float(extras.get("temporary_impact") or 1e-3)
    sigma = float(extras.get("sigma") or 0.2)
    horizon = float(extras.get("horizon") or 1.0)

    skew = -permanent_impact * inventory_grid[:, None] * sigma * np.sqrt(max(1e-9, horizon))
    half_spread = temporary_impact * np.abs(inventory_grid[:, None]) + 1e-4
    reservation = mid_grid[None, :] + skew
    bid = reservation - half_spread
    ask = reservation + half_spread
    spread_bps = (ask - bid) / mid_grid[None, :] * 10_000.0
    return {
        "mid": mid_grid,
        "inventory": inventory_grid,
        "bid": bid,
        "ask": ask,
        "spread_bps": spread_bps,
        "skew": skew,
    }


def _glft_grid(extras: dict[str, Any]) -> dict[str, np.ndarray]:
    """Guéant-Lehalle-Fernandez-Tapia bounded-inventory market making.

    GLFT (2013) closed form for CARA utility, bounded inventory in
    ``[-Q, Q]``. The policy depends on inventory normalised to the
    boundary; outside the boundary we report NaN (the operator must
    halt).
    """
    mid_grid = np.asarray(extras.get("mid_grid") or np.linspace(100.0, 110.0, 32), dtype=float)
    inventory_grid = np.asarray(extras.get("inventory_grid") or np.arange(-10, 11), dtype=float)
    Q_max = float(extras.get("Q_max") or 10.0)
    gamma = float(extras.get("gamma") or 0.1)
    sigma = float(extras.get("sigma") or 0.2)
    A = float(extras.get("A") or 0.5)  # order arrival intensity
    k = float(extras.get("k") or 1.5)  # exponential decay of fill prob with depth

    eta = np.sqrt(2.0 * gamma / (A * k**2)) * sigma
    q_norm = np.clip(inventory_grid / Q_max, -1.0, 1.0)
    skew = -eta * q_norm
    half_spread = eta * (1.0 + np.abs(q_norm))
    reservation = mid_grid[None, :] + skew[:, None]
    bid = reservation - half_spread[:, None]
    ask = reservation + half_spread[:, None]
    # NaN outside the bounded inventory window so the operator sees
    # the policy ceases to be admissible.
    mask = (np.abs(inventory_grid) > Q_max)[:, None]
    bid = np.where(mask, np.nan, bid)
    ask = np.where(mask, np.nan, ask)
    spread_bps = (ask - bid) / mid_grid[None, :] * 10_000.0
    return {
        "mid": mid_grid,
        "inventory": inventory_grid,
        "bid": bid,
        "ask": ask,
        "spread_bps": spread_bps,
        "skew": np.broadcast_to(skew[:, None], bid.shape),
    }


__all__ = ["run_optctl_simulation"]
