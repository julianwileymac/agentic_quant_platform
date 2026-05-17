"""Risk-measure enumeration -- gs-quant-inspired.

Every measurable quantity the platform can compute is named here. The
:func:`aqp.risk.pricing.dispatch.calc` polymorphic dispatch reads the
enum value to find the right handler.

The enumeration is intentionally a catalogue, not a class hierarchy --
measures don't carry behaviour, just identity. Behaviour lives in the
per-measure handler registry.
"""
from __future__ import annotations

from enum import StrEnum


class RiskMeasure(StrEnum):
    """Every risk / pricing measure the platform can compute.

    Grouped by family:

    * **Pricing** -- the theoretical value of an instrument
    * **First-order Greeks** -- partial derivatives wrt single inputs
    * **Second-order Greeks** -- partial derivatives wrt two inputs
    * **VaR family** -- distributional tail measures
    * **Stress / scenario** -- worst-case impact under a named scenario
    * **Microstructure** -- LOB-level metrics
    """

    # ------ Pricing ------
    PRICE = "price"
    THEORETICAL_PRICE = "theoretical_price"
    MID_PRICE = "mid_price"
    MARK_PRICE = "mark_price"
    IMPLIED_VOL = "implied_vol"

    # ------ First-order Greeks ------
    DELTA = "delta"
    GAMMA = "gamma"
    THETA = "theta"
    VEGA = "vega"
    RHO = "rho"
    PSI = "psi"  # FX rho (dividend rho)

    # ------ Second-order / cross Greeks ------
    VANNA = "vanna"
    VOLGA = "volga"
    CHARM = "charm"
    SPEED = "speed"
    ZOMMA = "zomma"
    COLOR = "color"

    # ------ Rates ------
    IR_DELTA = "ir_delta"
    IR_GAMMA = "ir_gamma"
    IR_ANNUAL_IMPLIED_VOL = "ir_annual_implied_vol"
    KRD = "krd"  # key-rate duration
    DV01 = "dv01"
    CONVEXITY = "convexity"

    # ------ Credit ------
    CS01 = "cs01"
    JTD = "jtd"  # jump-to-default

    # ------ Equity ------
    EQ_DELTA = "eq_delta"
    EQ_VEGA = "eq_vega"

    # ------ Aggregate / portfolio ------
    NOTIONAL = "notional"
    GROSS_EXPOSURE = "gross_exposure"
    NET_EXPOSURE = "net_exposure"

    # ------ VaR family ------
    VAR_95 = "var_95"
    VAR_99 = "var_99"
    TVAR_95 = "tvar_95"
    TVAR_99 = "tvar_99"
    MARGINAL_VAR = "marginal_var"
    COMPONENT_VAR = "component_var"

    # ------ Stress / scenario ------
    STRESS_LOSS = "stress_loss"
    SCENARIO_PNL = "scenario_pnl"

    # ------ Microstructure ------
    LOB_DEPTH = "lob_depth"
    LOB_PRESSURE = "lob_pressure"
    QUEUE_POSITION = "queue_position"


__all__ = ["RiskMeasure"]
