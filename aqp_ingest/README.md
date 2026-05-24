# aqp-ingest

Customer-facing self-service ingestion plane for the Agentic Quant
Platform.

## What this is

`aqp_ingest/` is the standalone boundary that:

- ships custom Airbyte CDK extensions (`RateLimitedHttpStream`,
  `PointInTimeIncrementalCursor`, `QuestDBDestination`),
- curates financial-API connectors (Polygon 4 streams, Databento,
  Alpaca, IEX Cloud, Bloomberg BPIPE, Refinitiv Elektron, FRED, etc.),
- manages multi-workspace Airbyte deployments via the official
  Terraform provider v1.2.1,
- seeds a 50+ template connector marketplace,
- runs the dbt-loom v0.9.4 registry sidecar.

Every connector resolves vendor credentials through the BYOK
`BrokerCredentialStore` (priority 4) and meters every outbound
request through the `aqp_ratelimit` token-bucket service.

## Layout

```
aqp_ingest/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── src/aqp_ingest_cdk/
│   ├── __init__.py
│   ├── streams.py            # RateLimitedHttpStream + PointInTimeIncrementalCursor
│   ├── destinations.py       # QuestDBDestination + IcebergBronzeDestination
│   ├── credentials.py        # ResolverBackedConfigProvider
│   └── lineage.py            # OpenLineage emit on sync complete
├── connectors/
│   ├── polygon/
│   │   ├── aggregates.py
│   │   ├── trades.py
│   │   ├── quotes.py
│   │   └── options_chain.py
│   ├── databento/historical.py
│   ├── alpaca/bars.py
│   ├── alpaca/trades.py
│   ├── iex/snapshots.py
│   └── bloomberg/bpipe.py
├── controller/
│   ├── __init__.py
│   ├── workspaces.py         # per-team workspace provisioning
│   └── terraform_emit.py     # generates airbyte connections.tf
├── marketplace/
│   ├── __init__.py
│   └── seed/
│       ├── polygon_aggregates.yaml
│       ├── databento_historical.yaml
│       └── ...
├── dbt_loom/
│   ├── __init__.py
│   └── registry.py           # publishes manifest.json to S3
├── tasks/
│   ├── __init__.py
│   └── airbyte_sync_webhook.py
├── api/
│   └── routes/
│       └── airbyte_webhooks.py
├── configs/
│   └── workspaces.yaml
└── tests/
    └── ...
```

## Hard boundaries

See [AGENTS.md](AGENTS.md) for the full contract.

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
```
