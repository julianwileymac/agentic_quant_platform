# Live Market Data

## Endpoints

- ``POST /live/subscribe`` — body ``{venue, symbols, poll_cadence_seconds?}``.
  Spawns a server-side task that reads from an
  :class:`aqp.core.interfaces.IMarketDataFeed` and publishes each bar
  onto Redis channel ``aqp:live:<channel_id>``.
- ``GET /live/stream/{channel_id}`` — WebSocket that forwards every
  published bar to the client.
- ``GET /live/subscriptions`` — list active channels.
- ``DELETE /live/subscribe/{channel_id}`` — stop the orchestrator task
  and release the feed.

## Venues

| Venue | Requires | Notes |
|---|---|---|
| ``simulated`` | Nothing | Deterministic sine-wave replay. Great for UI smoke-tests. |
| ``alpaca`` | ``.[alpaca]`` + ``AQP_ALPACA_API_KEY`` / ``AQP_ALPACA_SECRET_KEY`` | Equities / crypto live WS bars. |
| ``ibkr`` | ``.[ibkr]`` + running TWS / IB Gateway at ``AQP_IBKR_HOST``/``AQP_IBKR_PORT`` | 5-second real-time bars. |
| ``kafka`` | ``.[streaming]`` + ``AQP_KAFKA_BOOTSTRAP`` pointing at the streaming platform | Consumes the Flink-processed stream (default ``features.normalized.v1``). Pass ``kafka_topic`` + ``kafka_emit_as`` in the subscribe request to read other schemas (``market.bar.v1``, ``features.signals.v1``, ...). |

## UI

The **Live Market** page (``/live``) lets you pick a venue, enter a
ticker list, subscribe, and inspect streaming price tiles with a
one-click **Unsubscribe**.

## Code usage

```python
import httpx

api = "http://localhost:8000"
resp = httpx.post(f"{api}/live/subscribe", json={"venue": "alpaca", "symbols": ["AAPL", "MSFT"]}).json()
print(resp["stream_url"])  # /live/stream/<channel_id>

# Consume the Flink-processed feed instead (Kafka venue)
resp = httpx.post(
    f"{api}/live/subscribe",
    json={
        "venue": "kafka",
        "symbols": ["AAPL.NASDAQ", "MSFT.NASDAQ"],
        "kafka_topic": "features.normalized.v1",
        "kafka_emit_as": "bar",
    },
).json()
```

## Kafka streaming architecture

See [streaming.md](streaming.md) for the end-to-end pipeline that powers
the ``kafka`` venue: IBKR + Alpaca ingesters, Avro-schemed Kafka topics,
and the PyFlink jobs that normalize and score the stream before the
feed consumes it.
