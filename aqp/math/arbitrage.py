"""Statistical-arbitrage math primitives.

Single home for the primitives Phase 4 (and onwards) calls. The
module is intentionally synchronous + numpy/pandas-only -- callers
that want async dispatch wrap them in a Celery task.

The functions stay deliberately thin: ADF + Engle-Granger reuse the
existing primitives in :mod:`aqp.data.cointegration`; the new
primitives shipped here are:

* :func:`johansen_test` -- multivariate (n>=2) cointegration
* :func:`rolling_zscore` -- standard z-score over a window
* :func:`half_life` -- Ornstein-Uhlenbeck mean-reversion timescale
* :func:`pair_signal` -- ENTRY / EXIT / HOLD signal generator
* :func:`ah_share_basis` -- A-share <-> H-share basis (per report)
* :func:`adr_basis` -- ADR <-> underlying foreign equity basis
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class JohansenResult:
    """Outcome of a Johansen multivariate cointegration test.

    The Johansen test answers "how many independent cointegrating
    relationships exist among ``n`` series?" -- ``rank`` cointegrating
    vectors are reported, with trace + max-eigenvalue statistics and
    their critical values at 95% and 99%.
    """

    rank: int
    n_series: int
    deterministic: str  # constant | trend | none
    eig: list[float] = field(default_factory=list)
    trace_stat: list[float] = field(default_factory=list)
    max_eigen_stat: list[float] = field(default_factory=list)
    crit_trace_95: list[float] = field(default_factory=list)
    crit_max_eigen_95: list[float] = field(default_factory=list)
    crit_trace_99: list[float] = field(default_factory=list)
    crit_max_eigen_99: list[float] = field(default_factory=list)
    cointegrating_vectors: list[list[float]] = field(default_factory=list)
    is_cointegrated_95: bool = False
    is_cointegrated_99: bool = False
    error: str | None = None


@dataclass(slots=True)
class HalfLifeResult:
    """Ornstein-Uhlenbeck mean-reversion timescale."""

    half_life: float
    theta: float  # mean-reversion speed
    mean: float
    is_stationary: bool
    p_value: float | None = None


class SignalKind(StrEnum):
    HOLD = "hold"
    ENTRY_LONG_SPREAD = "entry_long_spread"
    ENTRY_SHORT_SPREAD = "entry_short_spread"
    EXIT_LONG_SPREAD = "exit_long_spread"
    EXIT_SHORT_SPREAD = "exit_short_spread"


@dataclass(slots=True)
class PairSignal:
    """Per-bar signal from a pair-trading state machine."""

    kind: SignalKind
    zscore: float
    spread: float
    is_in_position: bool = False
    half_life: float | None = None
    reason: str = ""


@dataclass(slots=True)
class BasisResult:
    """Cross-market basis snapshot (A/H share, ADR/underlying)."""

    price_a: float
    price_b: float
    conversion_ratio: float
    fx_rate: float
    implied_price: float  # price_a translated into B's market
    basis: float  # price_b - implied_price
    basis_pct: float  # basis / implied_price
    cost_adjusted_basis: float  # basis - fees
    is_arbitrage: bool
    arbitrage_direction: str = "none"  # buy_a_sell_b | buy_b_sell_a | none


# ---------------------------------------------------------------------------
# Johansen multivariate cointegration
# ---------------------------------------------------------------------------


def johansen_test(
    df: "pd.DataFrame",
    *,
    deterministic: str = "constant",
    k_ar_diff: int = 1,
    level_95: bool = True,
) -> JohansenResult:
    """Johansen test for multivariate cointegration.

    ``df`` is a wide pandas DataFrame with one column per series (>=2).
    ``deterministic`` is ``constant``, ``trend``, or ``none``. The
    test runs both the trace statistic and the max-eigenvalue
    statistic; ``rank`` is set to the largest rank at which both
    statistics reject the null at the 95% level (when ``level_95=True``).

    The test is delegated to ``statsmodels.tsa.vector_ar.vecm.coint_johansen``
    when available; on import failure the result carries an explanatory
    error string so the caller can fall back to Engle-Granger.
    """
    try:
        import numpy as np  # noqa: F401
        from statsmodels.tsa.vector_ar.vecm import coint_johansen
    except Exception as exc:  # noqa: BLE001
        return JohansenResult(
            rank=0,
            n_series=len(df.columns) if hasattr(df, "columns") else 0,
            deterministic=deterministic,
            error=f"statsmodels unavailable: {exc}",
        )
    if df.shape[1] < 2:
        return JohansenResult(
            rank=0,
            n_series=df.shape[1],
            deterministic=deterministic,
            error="Johansen requires at least 2 series",
        )
    if df.shape[0] < 30:
        return JohansenResult(
            rank=0,
            n_series=df.shape[1],
            deterministic=deterministic,
            error="Johansen requires at least 30 observations",
        )

    # det_order: -1 = no trend or constant, 0 = constant, 1 = trend
    det_order = {"none": -1, "constant": 0, "trend": 1}.get(deterministic, 0)
    try:
        result = coint_johansen(
            df.dropna().values, det_order=det_order, k_ar_diff=k_ar_diff
        )
    except Exception as exc:  # noqa: BLE001
        return JohansenResult(
            rank=0,
            n_series=df.shape[1],
            deterministic=deterministic,
            error=str(exc),
        )

    trace_stat = list(map(float, result.lr1))
    max_eigen_stat = list(map(float, result.lr2))
    crit_trace = result.cvt  # shape (n, 3) -- 90/95/99
    crit_max_eigen = result.cvm
    crit_trace_95 = list(map(float, crit_trace[:, 1]))
    crit_trace_99 = list(map(float, crit_trace[:, 2]))
    crit_max_eigen_95 = list(map(float, crit_max_eigen[:, 1]))
    crit_max_eigen_99 = list(map(float, crit_max_eigen[:, 2]))

    rank = 0
    for i in range(len(trace_stat)):
        if trace_stat[i] > crit_trace_95[i] and max_eigen_stat[i] > crit_max_eigen_95[i]:
            rank = i + 1
        else:
            break

    is_coint_95 = rank > 0
    is_coint_99 = False
    for i in range(len(trace_stat)):
        if trace_stat[i] > crit_trace_99[i] and max_eigen_stat[i] > crit_max_eigen_99[i]:
            is_coint_99 = True
            break

    vectors: list[list[float]] = []
    if hasattr(result, "evec"):
        vectors = [list(map(float, row)) for row in result.evec.T[:rank or 1]]

    return JohansenResult(
        rank=int(rank),
        n_series=df.shape[1],
        deterministic=deterministic,
        eig=list(map(float, result.eig)),
        trace_stat=trace_stat,
        max_eigen_stat=max_eigen_stat,
        crit_trace_95=crit_trace_95,
        crit_max_eigen_95=crit_max_eigen_95,
        crit_trace_99=crit_trace_99,
        crit_max_eigen_99=crit_max_eigen_99,
        cointegrating_vectors=vectors,
        is_cointegrated_95=is_coint_95,
        is_cointegrated_99=is_coint_99,
    )


# ---------------------------------------------------------------------------
# Rolling z-score + half-life
# ---------------------------------------------------------------------------


def rolling_zscore(spread: "pd.Series", window: int) -> "pd.Series":
    """Rolling z-score: ``(x - rolling_mean) / rolling_std``.

    NaN for the first ``window-1`` observations.
    """
    rolling_mean = spread.rolling(window=window, min_periods=window).mean()
    rolling_std = spread.rolling(window=window, min_periods=window).std()
    return (spread - rolling_mean) / rolling_std


def half_life(spread: "pd.Series") -> HalfLifeResult:
    """Estimate the mean-reversion half-life of a stationary spread.

    Fits the AR(1) model ``Delta s_t = theta * (s_{t-1} - mu) +
    epsilon_t`` and reports ``half_life = ln(2) / theta``.

    For a non-mean-reverting spread (theta >= 0), the half-life is
    infinity and ``is_stationary`` is False.
    """
    try:
        import numpy as np
        import pandas as pd  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return HalfLifeResult(
            half_life=float("inf"),
            theta=0.0,
            mean=0.0,
            is_stationary=False,
            p_value=None,
        )
    s = spread.dropna().astype(float)
    if len(s) < 30:
        return HalfLifeResult(
            half_life=float("inf"), theta=0.0, mean=float(s.mean() if len(s) else 0.0),
            is_stationary=False, p_value=None,
        )
    s_lag = s.shift(1).dropna()
    delta = s.diff().dropna()
    common_idx = s_lag.index.intersection(delta.index)
    s_lag = s_lag.loc[common_idx].values
    delta = delta.loc[common_idx].values
    s_lag_centered = s_lag - s_lag.mean()
    # OLS slope: delta = beta * (s_lag - mean) + eps
    if (s_lag_centered ** 2).sum() == 0:
        beta = 0.0
    else:
        beta = float(
            (s_lag_centered * delta).sum() / (s_lag_centered ** 2).sum()
        )
    is_stationary = beta < 0
    if beta < 0:
        hl = float(-math.log(2.0) / beta)
    else:
        hl = float("inf")
    return HalfLifeResult(
        half_life=hl,
        theta=float(-beta),
        mean=float(s_lag.mean()),
        is_stationary=is_stationary,
        p_value=None,
    )


def pair_signal(
    spread: "pd.Series",
    *,
    entry_threshold: float = 2.0,
    exit_threshold: float = 0.5,
    window: int = 60,
    is_in_position: bool = False,
    half_life_min: float | None = None,
) -> PairSignal:
    """Generate a per-bar pair-trading signal from a spread series.

    Reads the LATEST observation of the spread and the rolling
    z-score. Returns one of:

    * ``ENTRY_LONG_SPREAD`` -- z >= +entry_threshold (spread is high; sell A, buy B)
    * ``ENTRY_SHORT_SPREAD`` -- z <= -entry_threshold (spread is low; buy A, sell B)
    * ``EXIT_LONG_SPREAD`` -- z reverts toward zero from above
    * ``EXIT_SHORT_SPREAD`` -- z reverts toward zero from below
    * ``HOLD`` -- otherwise
    """
    try:
        zseries = rolling_zscore(spread, window=window)
    except Exception:  # noqa: BLE001
        return PairSignal(kind=SignalKind.HOLD, zscore=0.0, spread=float(spread.iloc[-1] if len(spread) else 0.0))
    if zseries.empty:
        return PairSignal(kind=SignalKind.HOLD, zscore=0.0, spread=float(spread.iloc[-1] if len(spread) else 0.0))

    z = float(zseries.iloc[-1])
    last_spread = float(spread.iloc[-1])

    hl_result = half_life(spread)
    if half_life_min is not None and (
        not hl_result.is_stationary or hl_result.half_life > half_life_min
    ):
        return PairSignal(
            kind=SignalKind.HOLD,
            zscore=z,
            spread=last_spread,
            is_in_position=is_in_position,
            half_life=hl_result.half_life,
            reason=f"half-life {hl_result.half_life:.1f} > minimum {half_life_min}",
        )

    if is_in_position:
        if -exit_threshold <= z <= exit_threshold:
            # Reverted -> exit. We don't know which direction we entered;
            # leave that bookkeeping to the caller.
            return PairSignal(
                kind=SignalKind.EXIT_LONG_SPREAD
                if z >= 0
                else SignalKind.EXIT_SHORT_SPREAD,
                zscore=z,
                spread=last_spread,
                is_in_position=True,
                half_life=hl_result.half_life,
                reason="reverted within exit band",
            )
        return PairSignal(
            kind=SignalKind.HOLD,
            zscore=z,
            spread=last_spread,
            is_in_position=True,
            half_life=hl_result.half_life,
            reason="position open, no exit signal",
        )

    if z >= entry_threshold:
        return PairSignal(
            kind=SignalKind.ENTRY_LONG_SPREAD,
            zscore=z,
            spread=last_spread,
            half_life=hl_result.half_life,
            reason=f"z={z:.2f} above entry threshold",
        )
    if z <= -entry_threshold:
        return PairSignal(
            kind=SignalKind.ENTRY_SHORT_SPREAD,
            zscore=z,
            spread=last_spread,
            half_life=hl_result.half_life,
            reason=f"z={z:.2f} below entry threshold",
        )
    return PairSignal(
        kind=SignalKind.HOLD,
        zscore=z,
        spread=last_spread,
        half_life=hl_result.half_life,
        reason="z within neutral band",
    )


# ---------------------------------------------------------------------------
# Cross-market basis (A/H, ADR/underlying)
# ---------------------------------------------------------------------------


def ah_share_basis(
    a_price: float,
    h_price: float,
    *,
    fx_rate: float,
    conversion_ratio: float = 1.0,
    transaction_cost_bps: float = 20.0,
    threshold_bps: float = 100.0,
) -> BasisResult:
    """A-share <-> H-share basis snapshot.

    The same Chinese company can be dual-listed -- A-shares trade in
    CNY on mainland venues (SSE / SZSE), H-shares trade in HKD on
    HKEX. The companies legally hold identical economic rights, so
    the basis should mean-revert toward zero. Periodic, violent
    divergence is the arbitrage opportunity.

    Args:
        a_price: A-share price in CNY
        h_price: H-share price in HKD
        fx_rate: CNY per HKD (so a_price in HKD = a_price / fx_rate)
        conversion_ratio: usually 1.0 (same per-share economic rights)
        transaction_cost_bps: round-trip cost
        threshold_bps: minimum basis to flag as arbitrage opportunity

    Returns a :class:`BasisResult` with arbitrage direction.
    """
    if fx_rate <= 0:
        raise ValueError("fx_rate must be positive (CNY per HKD)")
    # Convert A-share price to HKD using the FX rate.
    a_in_hkd = a_price / fx_rate * conversion_ratio
    basis = h_price - a_in_hkd
    basis_pct = basis / a_in_hkd if a_in_hkd else 0.0
    cost_bps = transaction_cost_bps / 10000.0
    cost_adjusted = basis - cost_bps * a_in_hkd
    basis_bps = basis_pct * 10000.0
    is_arb = abs(basis_bps) > threshold_bps
    direction = "none"
    if is_arb:
        direction = "buy_a_sell_b" if basis > 0 else "buy_b_sell_a"
    return BasisResult(
        price_a=float(a_price),
        price_b=float(h_price),
        conversion_ratio=float(conversion_ratio),
        fx_rate=float(fx_rate),
        implied_price=float(a_in_hkd),
        basis=float(basis),
        basis_pct=float(basis_pct),
        cost_adjusted_basis=float(cost_adjusted),
        is_arbitrage=bool(is_arb),
        arbitrage_direction=direction,
    )


def adr_basis(
    adr_price: float,
    underlying_price: float,
    *,
    fx_rate: float,
    conversion_ratio: float,
    transaction_cost_bps: float = 30.0,
    depository_fee_bps: float = 5.0,
    threshold_bps: float = 80.0,
) -> BasisResult:
    """ADR / GDR <-> underlying foreign equity basis.

    The ADR trades in USD on a US venue; the underlying foreign
    equity trades in its home currency on its home venue. The
    conversion ratio (shares of underlying per receipt) is read
    directly from
    :class:`aqp.persistence.models_instruments.InstrumentADR`.

    Args:
        adr_price: ADR price in USD
        underlying_price: underlying foreign-equity price in its
            home currency
        fx_rate: home currency per USD (so underlying in USD =
            underlying_price / fx_rate)
        conversion_ratio: shares of underlying per receipt (e.g.
            BABA: 8 -- 1 ADR represents 8 H-shares)
        transaction_cost_bps: round-trip cost
        depository_fee_bps: annual depository fee, expressed as a
            spread adjustment
        threshold_bps: minimum basis to flag as arbitrage opportunity
    """
    if fx_rate <= 0:
        raise ValueError("fx_rate must be positive (home_ccy per USD)")
    underlying_in_usd_per_share = underlying_price / fx_rate
    implied_adr = underlying_in_usd_per_share * conversion_ratio
    basis = adr_price - implied_adr
    basis_pct = basis / implied_adr if implied_adr else 0.0
    total_cost_bps = transaction_cost_bps + depository_fee_bps
    cost_adjusted = basis - (total_cost_bps / 10000.0) * implied_adr
    basis_bps = basis_pct * 10000.0
    is_arb = abs(basis_bps) > threshold_bps
    direction = "none"
    if is_arb:
        # ADR-rich (positive basis) -> sell ADR, buy underlying
        direction = "sell_adr_buy_underlying" if basis > 0 else "buy_adr_sell_underlying"
    return BasisResult(
        price_a=float(underlying_price),
        price_b=float(adr_price),
        conversion_ratio=float(conversion_ratio),
        fx_rate=float(fx_rate),
        implied_price=float(implied_adr),
        basis=float(basis),
        basis_pct=float(basis_pct),
        cost_adjusted_basis=float(cost_adjusted),
        is_arbitrage=bool(is_arb),
        arbitrage_direction=direction,
    )


__all__ = [
    "BasisResult",
    "HalfLifeResult",
    "JohansenResult",
    "PairSignal",
    "SignalKind",
    "adr_basis",
    "ah_share_basis",
    "half_life",
    "johansen_test",
    "pair_signal",
    "rolling_zscore",
]
