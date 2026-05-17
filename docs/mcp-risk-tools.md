# Phase 5 DataMCP risk / pricing / arbitrage tools

> Status: **Phase 5 shipped**. Every Phase 1-4 capability is now
> exposed to agents through a DataMCPTool (AGENTS rule 22).

## Tool catalog by phase

### Phase 1 (instrument taxonomy + temporal identifiers + futures curves)

| Tool | Purpose |
| --- | --- |
| ``data.identity.resolve`` | Forward identifier resolution at ``as_of`` |
| ``data.identity.history`` | Walk every alias ever known for an entity |
| ``data.instruments.measures`` | List available metrics for an instrument |
| ``data.instruments.depositary_receipts`` | ADR / GDR rows + underlying linkage |
| ``data.instruments.reit_portfolio`` | REIT property-portfolio composition |
| ``data.futures.curve.list`` | Discover available futures curves |
| ``data.futures.curve.stitched`` | Roll-stitched continuous curve |

### Phase 4 (PricingContext + RiskMeasure + arbitrage primitives)

| Tool | Purpose |
| --- | --- |
| ``data.pricing.context.list`` | Audit recent pricing-context runs |
| ``data.pricing.greeks.option_chain`` | Chain-level Greek aggregation |
| ``data.risk.var.compute`` | Portfolio VaR + TVaR via historical/parametric/Cornish-Fisher |
| ``data.arbitrage.cointegration_pair`` | Engle-Granger pair test + half-life |
| ``data.arbitrage.johansen_basket`` | Multivariate Johansen cointegration |
| ``data.arbitrage.ah_share_basis`` | A/H share cross-market basis |
| ``data.arbitrage.adr_underlying_basis`` | ADR basis with conversion-ratio lookup from InstrumentADR |

### Pre-existing (kept for reference)

| Tool | Purpose |
| --- | --- |
| ``data.optimal_control.solve_hjb`` | Avellaneda-Stoikov / Cartea-Jaimungal HJB solve |
| ``data.optimal_control.evaluate_strategy`` | Replay LOB strategy on microstructure data |
| ``data.optimal_control.list_regimes`` | Latest toxicity-regime per symbol |
| ``data.catalog.browse`` / ``data.discovery.*`` / ``data.entities.*`` / ``data.streaming.*`` / ... | Catalog + discovery + entities + streaming |

## Hard rules an agent needs

* **Always go through MCP for portfolio / risk / pricing reads.**
  Never ``from aqp.persistence import ...`` inside agent code; never
  call ``calc(...)`` directly. The MCP boundary is the data-plane
  contract (AGENTS rule 22).

* **VaR / TVaR are point-in-time.** ``data.risk.var.compute`` takes
  a historical returns series; the result reflects the distribution
  of those observations. For a portfolio-wide VaR, fetch the
  portfolio's per-instrument returns and stack them column-wise --
  the tool computes a marginal-and-component decomposition.

* **Cross-market arbitrage tools read InstrumentADR.conversion_ratio
  automatically.** The Phase 1 row is the single source of truth.
  Override the ratio explicitly only for "what-if" analysis -- don't
  fold the override into a strategy spec (use the conversion_ratio
  override field on the alpha class, not the MCP call).

* **Pricing context audit is read-only.**
  ``data.pricing.context.list`` returns past runs; it doesn't trigger
  new ones. To launch a new pricing run, the agent uses the
  ``/risk/pricing/runs`` REST route (which wraps
  :class:`PricingContext` properly with experiment_id stamping).

## Worked example

An agent asked "Is BABA's ADR trading rich vs the 9988 underlying?"
would call, in order:

1. ``data.identity.resolve(scheme="ticker", value="BABA")`` -> get the
   instrument_id for the ADR
2. ``data.instruments.depositary_receipts(underlying_isin=...)`` to
   discover the conversion_ratio + the underlying's vt_symbol
3. ``data.arbitrage.adr_underlying_basis(adr_vt_symbol="BABA.NYSE",
   adr_price=..., underlying_price=..., fx_rate=...)`` -> get the
   basis + arbitrage direction

All three calls are MCP-mediated; no direct ORM or pricing-library
import. The lineage observer captures each call so the audit trail
is complete.
