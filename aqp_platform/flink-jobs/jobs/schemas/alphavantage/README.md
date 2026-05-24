# Alpha Vantage Avro schemas

Fourteen schemas, one per dedicated `alphavantage.*.v1` Kafka topic. All records
share a `ts_ns` (event time), `av_function` (AV API function that produced the
record), and `ingest_ts_ns` (producer-side timestamp).

| File | Topic | Notes |
|------|-------|-------|
| `alphavantage_quote_v1.avsc` | `alphavantage.quote.v1` | `GLOBAL_QUOTE` snapshots, keyed by symbol |
| `alphavantage_bar_v1.avsc` | `alphavantage.bar.v1` | OHLCV from INTRADAY/DAILY/WEEKLY/MONTHLY |
| `alphavantage_fx_v1.avsc` | `alphavantage.fx.v1` | FX rates + FX bars, keyed by currency pair |
| `alphavantage_crypto_v1.avsc` | `alphavantage.crypto.v1` | Crypto rates + bars |
| `alphavantage_news_v1.avsc` | `alphavantage.news.v1` | NEWS_SENTIMENT, keyed by article hash for compaction |
| `alphavantage_gainers_v1.avsc` | `alphavantage.gainers.v1` | TOP_GAINERS_LOSERS rows with bucket enum |
| `alphavantage_insider_v1.avsc` | `alphavantage.insider.v1` | INSIDER_TRANSACTIONS rows |
| `alphavantage_overview_v1.avsc` | `alphavantage.overview.v1` | Compacted company profile, keyed by symbol |
| `alphavantage_earnings_v1.avsc` | `alphavantage.earnings.v1` | EARNINGS, EARNINGS_CALENDAR, EARNINGS_ESTIMATES |
| `alphavantage_indicator_v1.avsc` | `alphavantage.indicator.v1` | 52 technical indicators in a map field |
| `alphavantage_options_v1.avsc` | `alphavantage.options.v1` | Realtime + historical option contracts |
| `alphavantage_commodity_v1.avsc` | `alphavantage.commodity.v1` | WTI/Brent/Natural gas/metals/ags/global index |
| `alphavantage_econ_v1.avsc` | `alphavantage.econ.v1` | Economic indicators (GDP, CPI, yields, etc.) |
| `alphavantage_deadletter_v1.avsc` | `alphavantage.deadletter.v1` | Failure envelope with retry hint |

These schemas are registered with Apicurio (Confluent-compatible wire format) by
the Alpha Vantage producer at startup. See `templates/alphavantage-producer/`.
