"""Risk-management models (Lean stage 4).

Three primary patterns live in this module:

- **Cap / scale models** — ``BasicRiskModel`` clips weights and rescales
  gross exposure, returning the (possibly empty) target list.
- **Per-symbol overrides** — ``TrailingStopRiskManagementModel`` walks
  open positions, tracks the unrealised-PnL peak in instance state, and
  emits ``target_weight=0`` overrides for any symbol whose peak-to-
  trough drop breaches a threshold. Mirrors Lean's
  ``TrailingStopRiskManagementModel.cs`` (``Algorithm.Framework/Risk/``).
- **Composition wrappers** — ``TVaRInterceptor`` wraps an inner
  ``IRiskManagementModel`` and short-circuits the entire target list to
  zero weight whenever the portfolio's Tail Value at Risk exceeds the
  configured threshold. Composition (rather than Python class
  decorators) matches Lean's ``CompositeRiskManagementModel`` pattern
  and keeps the registry surface clean.

All models honour the merge contract from Lean's ``ProcessInsights`` —
overrides for the same symbol take precedence over original targets.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.core.interfaces import IRiskManagementModel
from aqp.core.registry import register
from aqp.core.types import Direction, PortfolioTarget

logger = logging.getLogger(__name__)


@register("BasicRiskModel")
class BasicRiskModel(IRiskManagementModel):
    """Cap each position weight and bail on drawdown breaches."""

    def __init__(
        self,
        max_position_pct: float = 0.20,
        max_drawdown_pct: float = 0.15,
        leverage: float = 1.0,
    ) -> None:
        self.max_position_pct = float(max_position_pct)
        self.max_drawdown_pct = float(max_drawdown_pct)
        self.leverage = float(leverage)

    def evaluate(
        self, targets: list[PortfolioTarget], context: dict[str, Any]
    ) -> list[PortfolioTarget]:
        drawdown = float(context.get("drawdown", 0.0))
        if drawdown <= -self.max_drawdown_pct:
            return []

        cap = self.max_position_pct
        lev = self.leverage
        out: list[PortfolioTarget] = []
        for t in targets:
            clipped = max(-cap, min(cap, t.target_weight * lev))
            if abs(clipped) < 1e-4:
                continue
            out.append(
                PortfolioTarget(
                    symbol=t.symbol,
                    target_weight=clipped,
                    rationale=t.rationale,
                    horizon_days=t.horizon_days,
                )
            )
        total = sum(abs(t.target_weight) for t in out)
        if total > 1.0:
            scale = 1.0 / total
            out = [
                PortfolioTarget(
                    symbol=t.symbol,
                    target_weight=t.target_weight * scale,
                    rationale=t.rationale,
                    horizon_days=t.horizon_days,
                )
                for t in out
            ]
        return out


@register("NoOpRiskModel")
class NoOpRiskModel(IRiskManagementModel):
    """Pass-through — convenient for debugging."""

    def evaluate(self, targets, context):
        return list(targets)


@register("TrailingStopRiskManagementModel")
class TrailingStopRiskManagementModel(IRiskManagementModel):
    """Per-symbol unrealised-PnL peak tracker.

    Liquidates a symbol whenever its unrealised PnL drops by more than
    ``max_drawdown_percent`` from the highest unrealised PnL the position
    has reached since open. Direct port of Lean's
    ``TrailingStopRiskManagementModel.cs``:

    1. Walk every active position.
    2. Compute current unrealised PnL using the latest mark price.
    3. Track the running peak in instance state (``_peak_unrealised``).
    4. If ``(peak - current) / max(peak, eps) >= max_drawdown_percent``
       and ``peak > 0``, emit a ``PortfolioTarget(symbol, 0)`` override.
    5. When the position closes, drop the tracker entry so a fresh
       open starts a new peak.

    The override list is concatenated with the original targets; the
    engine's ``DistinctBy(Symbol)``-style merge picks the override row
    whenever a symbol appears in both sets, so trailing-stop liquidations
    cannot be unwound by a stale alpha signal in the same bar.

    Context expectations (populated by ``EventDrivenBacktester._run_impl``
    and ``PaperSession._on_bar``):

    - ``positions``: ``dict[vt_symbol, PositionData]`` — used for ``quantity``
      and ``average_price``.
    - ``prices``: ``dict[vt_symbol, float]`` — latest mark.
    """

    def __init__(self, max_drawdown_percent: float = 0.05) -> None:
        if max_drawdown_percent <= 0:
            raise ValueError("max_drawdown_percent must be > 0")
        self.max_drawdown_percent = float(max_drawdown_percent)
        self._peak_unrealised: dict[str, float] = {}

    @staticmethod
    def _unrealised_pnl(pos: Any, mark: float) -> float:
        """PnL accounting that respects long / short direction."""
        sign = 1.0 if getattr(pos, "direction", Direction.LONG) != Direction.SHORT else -1.0
        return (mark - float(pos.average_price)) * float(pos.quantity) * sign

    def evaluate(
        self,
        targets: list[PortfolioTarget],
        context: dict[str, Any],
    ) -> list[PortfolioTarget]:
        positions: dict[str, Any] = context.get("positions") or {}
        prices: dict[str, float] = context.get("prices") or {}
        if not positions:
            self._peak_unrealised.clear()
            return list(targets)

        overrides: list[PortfolioTarget] = []
        active: set[str] = set()
        for vt_symbol, pos in positions.items():
            qty = float(getattr(pos, "quantity", 0) or 0)
            if qty == 0:
                self._peak_unrealised.pop(vt_symbol, None)
                continue
            active.add(vt_symbol)
            mark = float(prices.get(vt_symbol, getattr(pos, "average_price", 0.0)))
            unrealised = self._unrealised_pnl(pos, mark)
            peak = max(self._peak_unrealised.get(vt_symbol, 0.0), unrealised)
            self._peak_unrealised[vt_symbol] = peak
            if peak <= 0:
                continue
            drop = (peak - unrealised) / peak
            if drop >= self.max_drawdown_percent:
                logger.info(
                    "trailing-stop: %s peak=%.4f current=%.4f drop=%.2f%% threshold=%.2f%%",
                    vt_symbol,
                    peak,
                    unrealised,
                    drop * 100,
                    self.max_drawdown_percent * 100,
                )
                overrides.append(
                    PortfolioTarget(
                        symbol=getattr(pos, "symbol", None),
                        target_weight=0.0,
                        rationale=(
                            f"trailing_stop {self.max_drawdown_percent:.1%} "
                            f"breached (drop={drop:.2%})"
                        ),
                    )
                )

        # Drop trackers for closed positions.
        for vt_symbol in list(self._peak_unrealised):
            if vt_symbol not in active:
                self._peak_unrealised.pop(vt_symbol, None)

        if not overrides:
            return list(targets)
        # Lean's ProcessInsights merge: overrides win for shared symbols.
        seen = {o.symbol.vt_symbol for o in overrides if o.symbol is not None}
        return overrides + [t for t in targets if t.symbol.vt_symbol not in seen]


@register("TVaRInterceptor")
class TVaRInterceptor(IRiskManagementModel):
    """Composition wrapper that flattens targets when portfolio TVaR breaches.

    Implements the formula from the institutional-grade refactor spec:

    .. math::

       \\text{TVaR}_{\\alpha} = \\mu + \\sigma \\,
           \\frac{\\phi(\\Phi^{-1}(\\alpha))}{1 - \\alpha}

    where :math:`\\phi` is the standard normal PDF and :math:`\\Phi^{-1}` the
    inverse standard normal CDF. The expression is the closed-form expected
    shortfall under a Gaussian return assumption — fast to evaluate per
    bar and a useful upper bound on the empirical CVaR for well-behaved
    portfolios.

    Intercepts the ``inner.evaluate(...)`` output rather than replacing it,
    so all the cap / scale / per-symbol-override semantics from the wrapped
    model are honoured first; the interceptor only triggers when even the
    risk-adjusted target list is too risky in the tails.

    Context expectations:

    - ``history``: pandas DataFrame with at least ``timestamp``, ``vt_symbol``,
      ``close`` columns. Used to compute the per-symbol return panel from
      which the portfolio's :math:`\\mu` and :math:`\\sigma` are estimated.
    """

    def __init__(
        self,
        inner: IRiskManagementModel,
        *,
        alpha: float = 0.95,
        max_tvar: float = 0.10,
        lookback_days: int = 252,
    ) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        if max_tvar <= 0:
            raise ValueError("max_tvar must be > 0")
        if lookback_days < 2:
            raise ValueError("lookback_days must be >= 2")
        self.inner = inner
        self.alpha = float(alpha)
        self.max_tvar = float(max_tvar)
        self.lookback_days = int(lookback_days)

    @staticmethod
    def tvar_normal(mu: float, sigma: float, alpha: float) -> float:
        """Closed-form Gaussian TVaR (Expected Shortfall).

        Returns ``mu + sigma * (phi(InvPhi(alpha)) / (1 - alpha))``.
        Pure function — exposed as a staticmethod so tests can verify the
        numerical kernel without constructing a full interceptor.
        """
        from scipy.stats import norm

        return float(mu) + float(sigma) * (
            float(norm.pdf(norm.ppf(alpha))) / (1.0 - float(alpha))
        )

    def _portfolio_tvar(
        self,
        targets: list[PortfolioTarget],
        context: dict[str, Any],
    ) -> float | None:
        """Compute portfolio TVaR; returns ``None`` if inputs are insufficient."""
        if not targets:
            return None
        history = context.get("history")
        if history is None or len(history) == 0:
            return None
        try:
            import numpy as np
            import pandas as pd
        except ImportError:  # pragma: no cover
            return None

        try:
            frame = pd.DataFrame(history)
            if "timestamp" not in frame or "vt_symbol" not in frame or "close" not in frame:
                return None
            wide = (
                frame.pivot_table(
                    index="timestamp",
                    columns="vt_symbol",
                    values="close",
                    aggfunc="last",
                )
                .sort_index()
                .tail(self.lookback_days + 1)
            )
            if wide.shape[0] < 3:
                return None
            returns = wide.pct_change().dropna(how="all")
            if returns.empty:
                return None
            weights = pd.Series(
                {t.symbol.vt_symbol: float(t.target_weight) for t in targets if t.symbol},
                dtype=float,
            )
            common = [c for c in weights.index if c in returns.columns]
            if not common:
                return None
            w = weights.loc[common].to_numpy()
            r = returns[common].fillna(0.0).to_numpy()
            port_returns = r @ w
            mu = float(np.mean(port_returns))
            sigma = float(np.std(port_returns, ddof=1)) if len(port_returns) > 1 else 0.0
            if sigma == 0.0:
                return abs(mu)
            return abs(self.tvar_normal(mu, sigma, self.alpha))
        except Exception:
            logger.exception("TVaRInterceptor failed to compute portfolio TVaR")
            return None

    def evaluate(
        self,
        targets: list[PortfolioTarget],
        context: dict[str, Any],
    ) -> list[PortfolioTarget]:
        adjusted = self.inner.evaluate(targets, context)
        tvar = self._portfolio_tvar(adjusted, context)
        if tvar is None:
            return adjusted
        if tvar <= self.max_tvar:
            return adjusted
        logger.info(
            "TVaRInterceptor: tvar=%.4f exceeds max=%.4f (alpha=%.2f) — flattening %d targets",
            tvar,
            self.max_tvar,
            self.alpha,
            len(adjusted),
        )
        return [
            PortfolioTarget(
                symbol=t.symbol,
                target_weight=0.0,
                rationale=(
                    f"tvar {tvar:.4f} > max_tvar {self.max_tvar:.4f} "
                    f"(alpha={self.alpha})"
                ),
                horizon_days=t.horizon_days,
            )
            for t in adjusted
        ]


@register("VolTargetingRiskModel")
class VolTargetingRiskModel(IRiskManagementModel):
    """Scale every target weight to hit an annualised vol target.

    Reads per-symbol annualised vol from ``context["volatilities"]``
    (a ``{vt_symbol: sigma_annual}`` dict). Position weight becomes
    ``raw_weight * (target_vol / sigma_symbol)``, capped at
    ``max_weight``. Inspired by Moskowitz 2012 / Baltas 2020.
    """

    def __init__(
        self,
        target_vol: float = 0.20,
        max_weight: float = 1.0,
        min_sigma: float = 0.01,
    ) -> None:
        self.target_vol = float(target_vol)
        self.max_weight = float(max_weight)
        self.min_sigma = float(min_sigma)

    def evaluate(self, targets, context):
        vols = context.get("volatilities", {})
        out: list[PortfolioTarget] = []
        for t in targets:
            sigma = float(vols.get(t.symbol.vt_symbol, self.target_vol))
            sigma = max(sigma, self.min_sigma)
            scale = self.target_vol / sigma
            new_weight = max(-self.max_weight, min(self.max_weight, t.target_weight * scale))
            out.append(
                PortfolioTarget(
                    symbol=t.symbol,
                    target_weight=new_weight,
                    rationale=(t.rationale or "") + f"|vol_target({self.target_vol:.2f})",
                    horizon_days=t.horizon_days,
                )
            )
        return out


@register("MaxNotionalPerSymbolRiskModel")
class MaxNotionalPerSymbolRiskModel(IRiskManagementModel):
    """Cap each symbol's absolute notional exposure.

    Reads ``context["equity"]`` for the current account equity and
    enforces ``|target_weight * equity| <= max_notional_per_symbol``.
    Inspired by hftbacktest ``max_notional_position`` patterns.
    """

    def __init__(self, max_notional_per_symbol: float = 1_000_000.0) -> None:
        self.max_notional_per_symbol = float(max_notional_per_symbol)

    def evaluate(self, targets, context):
        equity = float(context.get("equity", 1.0))
        if equity <= 0:
            return list(targets)
        cap_weight = self.max_notional_per_symbol / equity
        out: list[PortfolioTarget] = []
        for t in targets:
            new_w = max(-cap_weight, min(cap_weight, t.target_weight))
            if new_w != t.target_weight:
                rationale = (t.rationale or "") + f"|notional_cap(${self.max_notional_per_symbol:,.0f})"
            else:
                rationale = t.rationale
            out.append(
                PortfolioTarget(
                    symbol=t.symbol,
                    target_weight=new_w,
                    rationale=rationale,
                    horizon_days=t.horizon_days,
                )
            )
        return out


__all__ = [
    "BasicRiskModel",
    "MaxNotionalPerSymbolRiskModel",
    "NoOpRiskModel",
    "TVaRInterceptor",
    "TrailingStopRiskManagementModel",
    "VolTargetingRiskModel",
]
