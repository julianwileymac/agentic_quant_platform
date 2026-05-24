# QuestDB

Phase 2b of the AQP infra-expansion plan. QuestDB is the high-
throughput hot-data tier for tick-level market data. It sits next
to (not in place of) Iceberg: rule 3 keeps
`iceberg_catalog.append_arrow` as the canonical lakehouse write
path; QuestDB serves trailing-window queries that agents need at
sub-second latency.

## Surface

| Artefact | Purpose |
|---|---|
| [`aqp/data/timeseries/questdb_client.py`](../aqp/data/timeseries/questdb_client.py) | Async PGWire client (port 8812). |
| [`aqp/data/timeseries/questdb_ingest.py`](../aqp/data/timeseries/questdb_ingest.py) | ILP TCP writer (port 9009). |
| [`aqp/data/datasets/kinds/questdb.py`](../aqp/data/datasets/kinds/questdb.py) | Kedro-style dataset kind (`kind="questdb"`). |
| `data.timeseries.questdb.list_tables` | MCP tool. |
| `data.timeseries.questdb.partition_info` | MCP tool. |
| `data.timeseries.questdb.sample_by` | MCP tool (rolling VWAP / 1m / 5m bars). |
| `data.timeseries.questdb.ilp_send` | Developer-only MCP tool. |
| [`scripts/cluster_install/install-questdb.sh`](../scripts/cluster_install/) | Bootstrap. |

## Production ingest path

```
producers -> Redpanda (market.l1.*, market.l2.*, execution.orders.*)
                  |
                  v
         Redpanda Connect (QuestDB sink, v4.37+)
                  |
                  v
              QuestDB (HOUR partitions, ILP)
```

The hand-rolled `QuestDBIngester` is the developer / smoke-test
fallback only. See
[`deployments/kubernetes/base-services/redpanda-connect/configmap.yaml`](../deployments/kubernetes/base-services/redpanda-connect/configmap.yaml).

## Allow-list

The MCP tool surface restricts table reads to:
`market_l1`, `market_l2`, `executions`, `agentic_state`,
`ohlcv_{1m,5m,15m,1h,1d}`. Adding a new table = extend
`_ALLOWED_TABLES` in
[`aqp/data/mcp/tools/questdb.py`](../aqp/data/mcp/tools/questdb.py).

## Topology entry

`services > questdb` (cluster `timeseries.questdb`, namespace
`aqp-timeseries`). Endpoints: `http`, `ilp_tcp`, `pgwire`.
