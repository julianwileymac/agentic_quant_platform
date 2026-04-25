# Streaming Architecture (IBKR + Alpaca -> Kafka -> Flink -> AQP)

This document describes the end-to-end live streaming pipeline that
turns broker events from Interactive Brokers and Alpaca into normalized
features + trading signals consumable by strategies, the paper trader,
and the `/live` API.

## High-level data flow

```
Interactive Brokers (TWS / IB Gateway)        Alpaca WebSocket
         |  ib-async                                |  alpaca-py
         v                                          v
   +--------------+                           +---------------+
   | IBKRIngester |                           | AlpacaIngester|
   +--------------+                           +---------------+
         |                                          |
         +-----------> Kafka (Strimzi KRaft) <------+
                |
                v
   market.trade.v1        market.quote.v1     market.bar.v1
   market.snapshot.v1     market.scanner.v1   market.contract.v1
   market.imbalance.v1    market.status.v1    market.correction.v1
                |
                v
        Flink Session Cluster (PyFlink)
        - dedupe
        - indicator_compute   -> features.indicators.v1
        - normalize_sink      -> features.normalized.v1  + PG/MinIO/VM
        - scanner_alert       -> features.signals.v1
                |
                v
   KafkaDataFeed (aqp.trading.feeds.kafka_feed.KafkaDataFeed)
                |
                v
        strategies / paper trader / /live WebSocket
```

## Components

### Ingesters (this repo)

Source: [aqp/streaming/](../aqp/streaming/).

- `kafka_producer.py` -- shared `confluent_kafka.Producer` with Avro
  encoding, Prometheus counters, and a deadletter fallback topic.
- `ingesters/ibkr.py` -- connects to TWS / IB Gateway via ``ib_async``
  and publishes:
  - `reqTickByTickData(AllLast)` -> `market.trade.v1`
  - `reqTickByTickData(BidAsk)`  -> `market.quote.v1`
  - `reqRealTimeBars(5s TRADES)` -> `market.bar.v1`
  - `reqMktData(genericTickList="225,232,233,236", snapshot=False)` ->
    `market.snapshot.v1` (honors
    `reqMarketDataType(AQP_STREAM_MARKET_DATA_TYPE)` so delayed / live
    paths share the same topic)
  - `reqContractDetails` -> `market.contract.v1` (compacted)
  - `reqScannerSubscription` polled every
    `AQP_STREAM_SCANNER_INTERVAL_SEC` when `AQP_STREAM_SCANNER_ENABLED`
- `ingesters/alpaca.py` -- connects to the Alpaca WSS feed selected by
  `AQP_ALPACA_FEED` (`iex` / `sip` / `delayed_sip`) and forwards every
  subscribed channel (trades/quotes/bars/updatedBars/dailyBars/statuses/
  imbalances/corrections/cancelErrors).
- `runtime.py` + `cli.py` -- launches the requested ingester(s) and
  exposes `/metrics` and `/healthz` on the configured ports.

Run locally:

```bash
pip install -e ".[alpaca,ibkr,streaming,otel]"
aqp-stream-ingest --venue all
```

Or in Kubernetes: `kubectl apply -k deploy/k8s/base/` (see below).

### Schemas

Source: [aqp/streaming/schemas/](../aqp/streaming/schemas/).

Twelve canonical Avro schemas, versioned with `_v1` suffixes. The file
layout is:

| Schema file               | Kafka topic                 |
|---------------------------|------------------------------|
| `market_trade_v1.avsc`    | `market.trade.v1`            |
| `market_quote_v1.avsc`    | `market.quote.v1`            |
| `market_bar_v1.avsc`      | `market.bar.v1`              |
| `market_snapshot_v1.avsc` | `market.snapshot.v1`         |
| `market_scanner_v1.avsc`  | `market.scanner.v1`          |
| `market_contract_v1.avsc` | `market.contract.v1`         |
| `market_imbalance_v1.avsc`| `market.imbalance.v1`        |
| `market_status_v1.avsc`   | `market.status.v1`           |
| `market_correction_v1.avsc`| `market.correction.v1`      |
| `features_indicators_v1.avsc`  | `features.indicators.v1` |
| `features_normalized_v1.avsc`  | `features.normalized.v1` |
| `features_signals_v1.avsc`     | `features.signals.v1`    |

Schemas are also copied into
`rpi_kubernetes/flink-jobs/jobs/schemas/` by
`bootstrap/scripts/build-flink-jobs.sh` so producers and Flink jobs
share byte-for-byte identical contracts.

### Kafka cluster (rpi_kubernetes)

- Deployed by Strimzi in the ``data-services`` namespace.
- Topics managed by `KafkaTopic` CRs in
  [rpi_kubernetes/kubernetes/base-services/kafka/topics.yaml](../../rpi_kubernetes/kubernetes/base-services/kafka/topics.yaml).
- Partitioning + retention tuned per topic (tick streams 1d, bars 7d,
  features 30d with compact+delete, `market.contract.v1` compacted
  forever, `market.deadletter.v1` 30d append-only).

### Flink jobs (rpi_kubernetes)

Source: [rpi_kubernetes/flink-jobs/jobs/](../../rpi_kubernetes/flink-jobs/jobs/).

Four PyFlink jobs run on the shared session cluster managed by the
Flink Kubernetes Operator (image
`ghcr.io/julianwiley/flink-trading:1.20` -- see
`rpi_kubernetes/flink-jobs/Dockerfile`).

1. **`dedupe.py`** -- de-duplicates trades/quotes/bars produced by both
   ingesters for the same symbol window.
2. **`indicator_compute.py`** -- per-symbol rolling statistics
   (SMA/EMA/RSI/MACD/BB/ATR/VWAP/OBV/lagged returns) over
   ``market.bar.v1`` -> `features.indicators.v1`.
3. **`normalize_sink.py`** -- running-mean/std normalization + fan-out
   to Kafka `features.normalized.v1`, PostgreSQL
   `flink_trading.signals`, MinIO Parquet archives, and
   VictoriaMetrics remote-write.
4. **`scanner_alert.py`** -- correlates `market.scanner.v1` rows with
   `market.bar.v1` movement to emit `features.signals.v1`
   records tagged with `source_job=scanner_alert`.

### KafkaDataFeed (this repo)

Source: [aqp/trading/feeds/kafka_feed.py](../aqp/trading/feeds/kafka_feed.py).

Closes the loop so aqp strategies consume Flink output as first-class
domain objects. Supports four emission modes:

| Mode      | Source topic              | AQP type                       |
|-----------|---------------------------|--------------------------------|
| `bar`     | `features.normalized.v1`  | `aqp.core.types.BarData`       |
| `quote`   | `market.quote.v1`         | `aqp.core.types.QuoteBar`      |
| `tick`    | `market.trade.v1`         | `aqp.core.types.TickData`      |
| `signal`  | `features.signals.v1`     | `aqp.core.types.Signal`        |

Use it manually:

```python
from aqp.trading.feeds.kafka_feed import KafkaDataFeed

feed = KafkaDataFeed(emit_as="signal")
await feed.connect()
async for sig in feed.stream():
    print(sig.vt_symbol, sig.direction, sig.strength)
```

Or via the existing `POST /live/subscribe`:

```bash
curl -X POST http://localhost:8000/live/subscribe \
  -H 'content-type: application/json' \
  -d '{"venue": "kafka", "symbols": ["AAPL.NASDAQ"],
       "kafka_topic": "features.normalized.v1", "kafka_emit_as": "bar"}'
```

## Deployment order

Bringing the pipeline up from a clean state:

1. `rpi_kubernetes/bootstrap/scripts/install-flink.sh` -- Strimzi
   operator + Kafka cluster + Flink Operator + session cluster.
2. `kubectl apply -f rpi_kubernetes/kubernetes/base-services/kafka/topics.yaml`
   -- creates the 12 canonical topics.
3. `rpi_kubernetes/bootstrap/scripts/build-flink-jobs.sh --push`
   -- builds `ghcr.io/julianwiley/flink-trading:1.20` (multi-arch) and
   uploads the PyFlink ``*.py`` files to
   ``s3://flink-jobs/`` in MinIO.
4. `kubectl apply -k rpi_kubernetes/kubernetes/base-services/flink/`
   -- picks up the new session-cluster image + job CRs (initially
   ``suspended``; flip ``state: running`` once the image and JAR URIs
   resolve).
5. In this repo: populate the broker secret and apply the aqp base:
   ```bash
   kubectl -n aqp create secret generic aqp-broker-secrets \
     --from-literal=AQP_ALPACA_API_KEY=... \
     --from-literal=AQP_ALPACA_SECRET_KEY=... \
     --from-literal=TWS_USERID=... \
     --from-literal=TWS_PASSWORD=...
   kubectl apply -k deploy/k8s/base/
   ```
6. Run `alembic upgrade head` against your PostgreSQL so the
   `flink_trading.*` tables exist before the `normalize_sink` job
   opens its JDBC upsert handles.

## Local development

`docker compose --profile streaming up -d` brings up a single-broker
KRaft Kafka + IB Gateway + both ingesters. IB Gateway login comes from
the `TWS_USERID` / `TWS_PASSWORD` environment variables (fallbacks to
empty strings so the other services still start). Topic creation is
done by the `kafka-init` one-shot.

## Operational notes

- **IB Gateway nightly reset**: the pod runs with
  `TWOFA_TIMEOUT_ACTION=restart` and the ingester wraps every attempt
  with exponential backoff. Expect a 2-5 minute gap around the reset.
- **IBKR client-id uniqueness**: the `IBKRIngester` uses
  `AQP_IBKR_CLIENT_ID + 200` so it never collides with the brokerage
  (``+0``) or the legacy `IBKRDataFeed` session feed (``+100``).
- **Alpaca single connection**: only one replica of
  `aqp-ingester-alpaca` can be live at a time -- Alpaca rejects
  concurrent WS sessions per API key.
- **Backpressure**: the Kafka producer has `queue.buffering.max.messages=200_000`.
  Prolonged outbound latency surfaces as `aqp_stream_produce_total{result="failed"}`
  in Prometheus and records eventually land on `market.deadletter.v1`.
- **Schema evolution**: the schemas are embedded in the ingester, the
  Flink image, and the KafkaDataFeed. Roll all three together when
  changing a schema; bump the suffix (`v2`) rather than mutate `v1` in
  place.
