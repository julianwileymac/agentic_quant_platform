# alphavantage-producer

Poll-and-emit Kafka producer for Alpha Vantage. Each stream (quote, bar, FX,
crypto, news, indicators, ...) runs as its own asyncio task that shares a
single rate limiter with the AV client engine. Every record is Avro-encoded
against the schemas under `flink-jobs/jobs/schemas/alphavantage/` and pushed to
the matching `alphavantage.*.v1` topic on the Strimzi cluster. Failures are
routed to `alphavantage.deadletter.v1` with a typed `error_kind`.

## Streams

| Stream | AV function(s) | Default cadence | Topic |
|--------|----------------|------------------|-------|
| `quote` | `GLOBAL_QUOTE` | 60s per symbol | `alphavantage.quote.v1` |
| `bar` | `TIME_SERIES_INTRADAY` (tail) | 300s per symbol | `alphavantage.bar.v1` |
| `news` | `NEWS_SENTIMENT` | 300s global | `alphavantage.news.v1` |
| `gainers` | `TOP_GAINERS_LOSERS` | 300s global | `alphavantage.gainers.v1` |
| `fx` | `CURRENCY_EXCHANGE_RATE` | 60s per pair | `alphavantage.fx.v1` |
| `crypto` | `CRYPTO_INTRADAY` (tail) | 120s per symbol | `alphavantage.crypto.v1` |
| `indicator` | 52 technical indicators | 600s per definition | `alphavantage.indicator.v1` |

The symbol universe + cadence are supplied via `config.yaml` mounted from a
ConfigMap (see `kubernetes/configmap.yaml`).

## Credentials

The API key resolves through `alphavantage_client._credentials.load_api_key`:
1. `ALPHAVANTAGE_API_KEY` env var.
2. `ALPHAVANTAGE_API_KEY_FILE` (default `/var/run/secrets/alphavantage/api-key`).

The Kafka SCRAM password for `producer-market` is mounted from the Strimzi
`KafkaUser` secret. The cluster CA cert is mounted from
`trading-kafka-cluster-ca-cert` into `/etc/kafka/ca/ca.crt`.

## Metrics

Exposed on `:9312/metrics` and scraped by the cluster Prometheus via annotations:

* `alphavantage_producer_messages_total{stream,topic,status}`
* `alphavantage_producer_api_request_seconds{stream,function}`
* `alphavantage_producer_rate_limiter_tokens`
* `alphavantage_producer_rate_limiter_requests_this_minute`
* `alphavantage_producer_deadletter_total{stream,reason}`

## Local dev

```bash
export ALPHAVANTAGE_API_KEY_FILE='C:\Users\Julian Wiley\Documents\alphavantage_api_token.txt'
export KAFKA_PRODUCER_BOOTSTRAP_SERVERS=localhost:9092
export KAFKA_PRODUCER_SECURITY_PROTOCOL=PLAINTEXT
python -m alphavantage_producer --config ./config.yaml
```
