# Instrument taxonomy

> Status: **Phase 1 shipped** (Alembic 0039). Adds REIT / mutual fund / OTC
> derivative / ADR / GDR as first-class polymorphic subclasses of
> :class:`aqp.persistence.models.Instrument` plus a registry table
> (``instrument_measures``) that catalogs which metrics are available for
> each instrument.

## Why

The legacy taxonomy treated REITs and depositary receipts as plain
``InstrumentEquity`` rows with a discriminator flag (``is_adr``), and
modelled OTC derivatives as opaque blobs. That worked while agents
only routed cash equities and listed options, but it broke as soon as
the platform tried to:

* compute the cross-market basis between an NYSE-listed ADR and its
  foreign common (no FK to the underlying, no conversion ratio, no
  depository bank metadata);
* run a REIT sector-rotation strategy (no FFO, no payout ratio, no
  property-portfolio composition);
* clear an OTC swap through a CCP (no LEI, no ISDA master agreement
  id, no notional / collateral fields).

Phase 1 lifts these shapes into first-class joined-table subclasses
with the columns the trading + risk + cross-market arbitrage paths
read directly.

## Taxonomy

| Class | SQL table | ``polymorphic_identity`` | InstrumentClass | AssetClass |
| --- | --- | --- | --- | --- |
| ``Equity`` | ``instrument_equity`` | ``spot`` | ``SPOT`` | ``EQUITY`` |
| ``ETF`` | ``instrument_etf`` | ``etf`` | ``ETF`` | ``EQUITY`` |
| ``IndexInstrument`` | ``instrument_index`` | ``index`` | ``INDEX`` | ``INDEX`` |
| ``Bond`` | ``instrument_bond`` | ``bond`` | ``BOND`` | ``RATES`` |
| ``FuturesContract`` | ``instrument_future`` | ``future`` | ``FUTURE`` | ``COMMODITY`` |
| ``OptionContract`` | ``instrument_option`` | ``option`` | ``OPTION`` | ``EQUITY`` |
| ``CurrencyPair`` | ``instrument_fx_pair`` | ``fx_pair`` | ``SPOT`` | ``FX`` |
| ``CryptoToken`` | ``instrument_crypto`` | ``crypto_token`` | ``CRYPTO_TOKEN`` | ``CRYPTO`` |
| ``Cfd`` | ``instrument_cfd`` | ``cfd`` | ``CFD`` | ``EQUITY`` |
| ``Commodity`` | ``instrument_commodity`` | ``spot_commodity`` | ``SPOT`` | ``COMMODITY`` |
| ``SyntheticInstrument`` | ``instrument_synthetic`` | ``synthetic`` | ``SYNTHETIC`` | ``MIXED`` |
| ``BettingInstrument`` | ``instrument_betting`` | ``betting`` | ``BETTING`` | ``EVENT`` |
| ``TokenizedAsset`` | ``instrument_tokenized_asset`` | ``nft`` | ``NFT`` | ``CRYPTO`` |
| **``REIT``** | **``instrument_reit``** | **``reit``** | **``REIT``** | **``EQUITY``** |
| **``MutualFund``** | **``instrument_mutual_fund``** | **``mutual_fund``** | **``MUTUAL_FUND``** | **``EQUITY``** |
| **``OTCDerivative``** | **``instrument_otc_derivative``** | **``otc_derivative``** | **``OTC_DERIVATIVE``** | **``MIXED``** |
| **``AmericanDepositaryReceipt``** | **``instrument_adr``** | **``adr``** | **``ADR``** | **``EQUITY``** |
| **``GlobalDepositaryReceipt``** | **``instrument_gdr``** | **``gdr``** | **``GDR``** | **``EQUITY``** |

Phase 1 rows are bolded.

### REIT

``InstrumentREIT`` adds the columns a REIT-aware strategy needs:

* ``reit_class`` -- ``equity``, ``mortgage``, ``hybrid``,
  ``public_non_listed``, ``private``
* ``property_sector`` -- ``residential``, ``commercial``, ``industrial``,
  ``healthcare``, ``data_center``, ``retail``, ``hospitality``,
  ``diversified``, ``infrastructure``, ``timber``
* ``property_portfolio_json`` -- list of property dicts (the discovery
  service surfaces these without spinning up a separate
  ``reit_properties`` table)
* ``distribution_yield`` / ``ffo_per_share`` / ``payout_ratio`` /
  ``debt_to_equity``

### Mutual fund

``InstrumentMutualFund`` covers open-end and closed-end funds. The
discriminator that distinguishes it from ``InstrumentETF`` is the
trading mechanism (end-of-day NAV vs intraday creation-redemption).

* ``fund_family`` (Vanguard / Fidelity / BlackRock / ...)
* ``share_class`` (A / B / C / I / R / Z / retail / institutional)
* ``fund_kind`` (open_end / closed_end / money_market / target_date /
  ucits / sicav)
* ``expense_ratio`` / ``management_fee`` / ``minimum_investment``

### OTC derivative

``InstrumentOTCDerivative`` is the catch-all for the OTC universe.
The ``instrument_kind`` discriminator selects the specific shape:

* ``swap`` / ``swaption`` / ``cap_floor`` / ``forward`` / ``exotic``
* ``variance_swap`` / ``credit_default_swap`` / ``total_return_swap`` /
  ``basket_swap``

Regulatory identity flows through ``counterparty_lei`` plus
``isda_master_agreement_id`` so trade-repository reconciliation
(DTCC, REGIS-TR) works without a separate registration step. The
``legs_json`` column stores the leg structure inline so a single
class supports the entire OTC universe without a tree of subclasses.

### ADR / GDR

Both subclasses carry:

* ``underlying_instrument_id`` -- FK to the foreign equity row
* ``conversion_ratio`` -- shares of foreign common per receipt
* ``depository_bank_name`` / ``depository_bank_lei``
* ADR adds ``sponsorship_level`` (I / II / III / 144A / Reg_S /
  unsponsored)
* GDR adds ``regulatory_regime`` (Reg_S / Rule_144A / Reg_S_144A /
  full_listing) plus a non-US ``listing_venue``

The Phase 4 cross-market basis algorithm reads
``adr.conversion_ratio`` and walks ``adr.underlying_instrument_id``
to fetch the local price directly -- no extra join needed.

## ``instrument_measures`` registry

Catalog of "what data exists for this instrument?". One row per
``(instrument_id, measure_type, frequency, dataset_field)`` tuple.

Common ``measure_type`` values: ``price``, ``volume``,
``open_interest``, ``implied_volatility``, ``dividend_yield``,
``ffo``, ``nav``, ``distribution``, ``greek_delta``, ``greek_gamma``,
``basis``, ``spread``, ``turnover``, ``bid_ask_spread``.

Common ``frequency`` values: ``tick``, ``second``, ``minute``,
``hour``, ``day``, ``week``, ``month``, ``quarter``, ``annual``,
``event_driven``, ``adhoc``.

Agents query this BEFORE drafting a SQL / Iceberg query via the
``data.instruments.measures`` DataMCP tool so they don't select a
column that doesn't exist for the instrument-frequency pair they
care about.

## How to add a new subclass

1. Add an :class:`InstrumentClass` enum value in
   [`aqp/core/domain/enums.py`](../aqp/core/domain/enums.py).
2. Add the matching joined-table SQL subclass in
   [`aqp/persistence/models_instruments.py`](../aqp/persistence/models_instruments.py).
   Set ``polymorphic_identity`` to the enum value.
3. Add the in-memory domain class in
   [`aqp/core/domain/instrument.py`](../aqp/core/domain/instrument.py)
   decorated with ``@register_instrument_class``.
4. Add an Alembic migration for the new table.
5. If the new class needs unique ``data.instruments.*`` access
   patterns, register a DataMCP tool under
   [`aqp/data/mcp/tools/instruments.py`](../aqp/data/mcp/tools/instruments.py).

## DataMCP surface

| Tool | Purpose |
| --- | --- |
| `data.instruments.measures` | Available metrics for an instrument |
| `data.instruments.depositary_receipts` | ADR / GDR with underlying-equity FK + conversion ratio |
| `data.instruments.reit_portfolio` | REIT property-portfolio composition + FFO / yield |
| `data.identity.resolve` | Forward identifier resolution at ``as_of`` |
| `data.identity.history` | Walk every alias ever known for an entity |
| `data.futures.curve.list` | Discover available futures curves |
| `data.futures.curve.stitched` | Roll-stitched continuous curves |
