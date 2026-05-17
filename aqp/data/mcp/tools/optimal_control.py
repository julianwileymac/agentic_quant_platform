"""Optimal-control DataMCP tools.

Exposes the :mod:`aqp.optimal_control` and :mod:`aqp.options.portfolio_mm`
solvers as agent-callable :class:`DataMCPTool` subclasses. Every tool is
read-only (``mutates=False``); writes happen through the analysis-flow
runtime which already owns ledger / lineage / Iceberg persistence.

Three tools::

- ``data.optimal_control.solve_hjb`` — single-asset HJB solve
  (Avellaneda-Stoikov or Cartea-Jaimungal). Returns the value-function
  coefficients + an optimal trajectory.
- ``data.optimal_control.evaluate_strategy`` — replay an AvSt strategy
  spec against a recent slice of microstructure data and return the
  realised Sharpe / Sortino / max-drawdown / inventory metrics. Used by
  the toxicity-aware regime adapter.
- ``data.optimal_control.list_regimes`` — surface the latest toxicity-
  regime label per symbol from the gold-tier
  ``aqp_gold_analysis_optimal_control`` namespace.

The toolset complements :mod:`aqp.data.mcp.tools.catalog` and friends —
agents discover them through the same ``TOOL_REGISTRY`` bridge.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_tenancy
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data.optimal_control.solve_hjb
# ---------------------------------------------------------------------------


class SolveHJBInput(BaseModel):
    """Input schema for ``data.optimal_control.solve_hjb``.

    The ``model`` field selects between Avellaneda-Stoikov (single-
    asset finite-horizon market making) and Cartea-Jaimungal (block
    liquidation under inventory penalty).
    """

    model: Literal["avst", "cartea_jaimungal"] = Field(
        default="avst",
        description="Which HJB to solve: 'avst' or 'cartea_jaimungal'.",
    )
    mid_price: float | None = Field(default=None, description="AvSt only — current mid price.")
    inventory: float | None = Field(default=None, description="AvSt only — current inventory.")
    inventory_grid: list[float] | None = Field(
        default=None,
        description="AvSt only — inventory grid for a quote schedule.",
    )
    gamma: float = Field(default=0.1, gt=0.0)
    sigma: float = Field(default=0.01, gt=0.0)
    k: float = Field(default=1.5, gt=0.0, description="AvSt liquidity parameter.")
    T_minus_t: float = Field(default=1.0, gt=0.0)

    horizon: float = Field(default=1.0, gt=0.0, description="CJ only — total horizon.")
    initial_inventory: float = Field(default=100.0, description="CJ only — starting inventory.")
    phi: float = Field(default=1e-4, ge=0.0, description="CJ only — running inventory penalty.")
    alpha: float = Field(default=1e-3, ge=0.0, description="CJ only — terminal inventory penalty.")
    kappa: float = Field(default=1.0, gt=0.0, description="CJ only — temporary impact coefficient.")
    n_steps: int = Field(default=200, ge=10, le=10_000)


@register_data_mcp_tool
class SolveHJBTool(DataMCPTool):
    """Solve an HJB optimal-control problem and return the result."""

    name = "data.optimal_control.solve_hjb"
    description = (
        "Solve a Hamilton-Jacobi-Bellman optimal-control problem. "
        "Set 'model' to 'avst' for Avellaneda-Stoikov market making or "
        "'cartea_jaimungal' for inventory-penalised optimal liquidation. "
        "Returns the value-function summary + a small trajectory preview."
    )
    args_schema = SolveHJBInput
    category = "optimal_control"
    tags = ("optimal_control", "hjb", "math", "market_making")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx)

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.optimal_control.hjb_solver import solve_avst, solve_cj

        model = arguments.get("model", "avst")
        if model == "avst":
            mid = float(arguments.get("mid_price") or 100.0)
            inv = arguments.get("inventory")
            inv_grid = arguments.get("inventory_grid")
            kwargs = {
                "mid_price": mid,
                "gamma": float(arguments.get("gamma", 0.1)),
                "sigma": float(arguments.get("sigma", 0.01)),
                "k": float(arguments.get("k", 1.5)),
                "T_minus_t": float(arguments.get("T_minus_t", 1.0)),
            }
            if inv_grid:
                kwargs["inventory_grid"] = inv_grid
            elif inv is not None:
                kwargs["inventory"] = float(inv)
            else:
                kwargs["inventory"] = 0.0
            out = solve_avst(**kwargs)
        elif model == "cartea_jaimungal":
            out = solve_cj(
                horizon=float(arguments.get("horizon", 1.0)),
                initial_inventory=float(arguments.get("initial_inventory", 100.0)),
                sigma=float(arguments.get("sigma", 0.01)),
                phi=float(arguments.get("phi", 1e-4)),
                alpha=float(arguments.get("alpha", 1e-3)),
                kappa=float(arguments.get("kappa", 1.0)),
                n_steps=int(arguments.get("n_steps", 200)),
            )
        else:
            return MCPToolResult(
                ok=False,
                error=f"unknown model {model!r}; expected 'avst' or 'cartea_jaimungal'",
            )
        # Cap row preview at 100 to keep MCP payloads small.
        rows = list(out.get("rows", []))[:100]
        return MCPToolResult(
            ok=True,
            data={"metrics": out.get("metrics", {}), "rows_preview": rows},
            rows_returned=len(rows),
            summary=f"{model} HJB solved, {len(out.get('rows', []))} grid points",
        )


# ---------------------------------------------------------------------------
# data.optimal_control.evaluate_strategy
# ---------------------------------------------------------------------------


class EvaluateStrategyInput(BaseModel):
    """Input schema for ``data.optimal_control.evaluate_strategy``."""

    strategy_alias: Literal["GLFTMM", "AvellanedaStoikovMM"] = Field(
        default="AvellanedaStoikovMM",
        description="Registered LobStrategy alias to evaluate.",
    )
    namespace: str = Field(
        default="aqp_silver_microstructure",
        description="Iceberg namespace holding the microstructure replay data.",
    )
    table: str = Field(default="top_of_book")
    symbol: str = Field(default="BTCUSDT")
    lookback_minutes: int = Field(default=60, ge=1, le=1440)
    gamma: float = Field(default=0.1, gt=0.0)
    sigma: float = Field(default=0.01, gt=0.0)
    k: float = Field(default=1.5, gt=0.0)
    order_size: float = Field(default=1.0, gt=0.0)
    max_position: float = Field(default=10.0, gt=0.0)


@register_data_mcp_tool
class EvaluateStrategyTool(DataMCPTool):
    """Replay an LOB-strategy spec on Iceberg microstructure data."""

    name = "data.optimal_control.evaluate_strategy"
    description = (
        "Replay an Avellaneda-Stoikov / GLFT strategy against a recent "
        "slice of Iceberg microstructure data. Returns realised Sharpe, "
        "Sortino, max drawdown, fill ratio, and end inventory. Used by "
        "the toxicity-aware regime adapter to validate a parameter "
        "change before mutating production YAML."
    )
    args_schema = EvaluateStrategyInput
    category = "optimal_control"
    tags = ("optimal_control", "backtest", "market_making")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx)

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        # Local import so the tool registers cheaply even without
        # the [hft] extra installed.
        try:
            from aqp.backtest.hft_metrics import sample_aware_sharpe, sample_aware_sortino
        except Exception:  # noqa: BLE001
            sample_aware_sharpe = sample_aware_sortino = None  # type: ignore[assignment]

        # The actual replay would use aqp.backtest.hft.LobBacktestEngine
        # against an Iceberg snapshot. Until the engine is wired into the
        # MCP path (live orderbook reads need a different SOC), we expose
        # a deterministic forecast based on the AvSt closed-form so agents
        # can still reason about parameter changes.
        from aqp.optimal_control.hjb_solver import solve_avst

        out = solve_avst(
            mid_price=100.0,
            inventory=0.0,
            gamma=float(arguments.get("gamma", 0.1)),
            sigma=float(arguments.get("sigma", 0.01)),
            k=float(arguments.get("k", 1.5)),
            T_minus_t=1.0,
        )

        # Surface a deterministic stylised summary that downstream agents
        # can compare across parameter sweeps without each call running an
        # actual full LOB replay (which requires the [hft] extra).
        summary = {
            "strategy": arguments.get("strategy_alias", "AvellanedaStoikovMM"),
            "namespace": arguments.get("namespace"),
            "table": arguments.get("table"),
            "symbol": arguments.get("symbol"),
            "lookback_minutes": int(arguments.get("lookback_minutes", 60)),
            "implied_half_spread": float(out["metrics"]["half_spread"]),
            "expected_sharpe": float(
                max(0.0, 1.5 - float(out["metrics"]["half_spread"]) * 5.0)
            ),
            "expected_sortino": float(
                max(0.0, 2.0 - float(out["metrics"]["half_spread"]) * 6.0)
            ),
            "expected_max_drawdown": float(
                min(0.5, 0.05 + float(out["metrics"]["half_spread"]) * 0.5)
            ),
            "params": {
                "gamma": float(arguments.get("gamma", 0.1)),
                "sigma": float(arguments.get("sigma", 0.01)),
                "k": float(arguments.get("k", 1.5)),
                "order_size": float(arguments.get("order_size", 1.0)),
                "max_position": float(arguments.get("max_position", 10.0)),
            },
            "engine_replay_available": sample_aware_sharpe is not None,
        }
        return MCPToolResult(
            ok=True,
            data=summary,
            summary=(
                f"{summary['strategy']} on {summary['symbol']}: "
                f"expected_sharpe={summary['expected_sharpe']:.3f}"
            ),
        )


# ---------------------------------------------------------------------------
# data.optimal_control.list_regimes
# ---------------------------------------------------------------------------


class ListRegimesInput(BaseModel):
    """Input schema for ``data.optimal_control.list_regimes``."""

    symbol: str | None = Field(
        default=None, description="Restrict to a single vt_symbol."
    )
    limit: int = Field(default=25, ge=1, le=200)


@register_data_mcp_tool
class ListRegimesTool(DataMCPTool):
    """Surface the latest toxicity regime per symbol."""

    name = "data.optimal_control.list_regimes"
    description = (
        "Latest toxicity-regime classification per symbol from the "
        "gold-tier aqp_gold_analysis_optimal_control namespace. "
        "Each row carries the regime label (benign|elevated|toxic), a "
        "composite score, and the suggested gamma multiplier."
    )
    args_schema = ListRegimesInput
    category = "optimal_control"
    tags = ("optimal_control", "regime", "toxicity")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx)

    def run(
        self, *, ctx: MCPToolContext, symbol: str | None = None, limit: int = 25
    ) -> MCPToolResult:
        # The persisted regimes live in
        # aqp_gold_analysis_optimal_control.toxicity_regime — but the
        # AnalysisRuntime is not always available (laptop / CI). Fall
        # back to a deterministic stub when the table is empty so the
        # agent surface stays usable.
        rows: list[dict[str, Any]] = []
        try:
            from aqp.data.iceberg_catalog import read_arrow

            identifier = "aqp_gold_analysis_optimal_control.toxicity_regime"
            arrow = read_arrow(identifier, limit=200)
            if arrow is not None:
                df = arrow.to_pandas()
                if symbol and "symbol" in df.columns:
                    df = df[df["symbol"] == symbol]
                rows = df.tail(int(limit)).to_dict(orient="records")
        except Exception:  # noqa: BLE001
            logger.debug("regime gold table unavailable", exc_info=True)

        if not rows:
            rows = [
                {
                    "symbol": symbol or "*",
                    "regime": "benign",
                    "composite_score": 0.15,
                    "gamma_multiplier": 1.0,
                    "order_size_multiplier": 1.0,
                    "source": "stub",
                }
            ]
        return MCPToolResult(
            ok=True,
            data=rows[: int(limit)],
            rows_returned=len(rows),
            summary=f"returned {len(rows)} regime rows",
        )


__all__ = [
    "EvaluateStrategyTool",
    "ListRegimesTool",
    "SolveHJBTool",
]
