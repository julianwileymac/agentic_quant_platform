# AGENTS.md

Agent contract for `aqp_ingest`.

## Purpose

This boundary owns the customer-facing self-service ingestion plane:
the [`aqp_ingest_cdk`](src/aqp_ingest_cdk/) Airbyte CDK extensions
(`RateLimitedHttpStream`, `PointInTimeIncrementalCursor`,
`QuestDBDestination`), every curated financial connector under
[`connectors/`](connectors/) (Polygon 4 streams, Databento, Alpaca,
IEX Cloud, Bloomberg BPIPE, Refinitiv Elektron, etc.), the Airbyte
controller ([`controller/`](controller/)) that manages workspaces +
connections via the official Airbyte Terraform provider v1.2.1, the
connector marketplace ([`marketplace/`](marketplace/)) seeded with
50+ templates that back the Phase 5 Vite catalog UI, and the
dbt-loom registry sidecar ([`dbt_loom/`](dbt_loom/)).

The boundary also owns the matching Celery tasks
([`tasks/`](tasks/)), FastAPI routes ([`api/routes/`](api/routes/)),
configs ([`configs/`](configs/)), and tests ([`tests/`](tests/)).

## Hard Boundaries

1. **All vendor API credentials resolve through `CredentialResolver`
   + `BrokerCredentialStore`.** Connectors call
   `get_resolver().resolve(CredentialKey(f"{provider}:{label}", "broker"))`
   and read fields via `Credential.require("api_key")`. NEVER read
   `settings.polygon_api_key` / `settings.tiingo_api_key` /
   `settings.alpha_vantage_api_key` / `settings.quandl_api_key` /
   `settings.coingecko_api_key` directly. The Phase 1 fetcher
   migration is the last time the monolith's `aqp/data/fetchers/api/`
   reads from `settings.*_api_key` — new fetchers under this
   boundary go through the resolver from day one.
2. **All connectors that hit a rate-limited vendor MUST inherit from
   [`RateLimitedHttpStream`](src/aqp_ingest_cdk/streams.py)** (NOT
   raw `airbyte_cdk.HttpStream`). The base wraps `_send_request`
   with `get_ratelimit_client().check()` from the
   [`aqp_ratelimit`](../aqp_ratelimit/) subsystem so the
   (user_id, service, key_id) bucket debits BEFORE the request
   fires. Generated `aqp/data/fetchers/userland/` stubs preserve
   this contract.
3. **Airbyte-synced raw data lands in
   `aqp_bronze_airbyte_<connector_slug>`** Iceberg namespaces (root
   AGENTS.md rule 21 + the new convention validated in
   `aqp/data/iceberg_catalog.py`). `connector_slug` is the
   lowercase, underscore-separated form of the connector id
   (e.g. `polygon_aggregates` → `aqp_bronze_airbyte_polygon_aggregates`).
4. **The Airbyte controller never imports `aqp.*` ORM models
   directly.** It speaks only Terraform + Airbyte HTTP API. The
   per-team `Organization.airbyte_workspace_id` column (Alembic
   0070) is the only Postgres handshake.
5. **Custom Python connectors stay under
   [`connectors/`](connectors/) (curated) or
   [`aqp/data/fetchers/userland/`](../aqp/data/fetchers/userland/)
   (operator-generated via the builder).** Both paths preserve
   rule 31's `AIRBYTE_ENABLE_UNSAFE_CODE`-free posture; neither
   accepts free-text Python an agent or operator typed into a web
   form.
6. **`AirbyteDataset` is the typed `BaseDataset` kind for
   Airbyte-synced data** (root AGENTS.md rule 29). The
   discriminator is `dataset_kind="airbyte"` on `dataset_catalogs`;
   the spec carries the workspace + connection + stream identifiers
   plus the bronze Iceberg namespace where the data lands.
7. **Dagster wiring goes through
   [`load_assets_from_airbyte_instance`](../aqp/dagster/assets/airbyte_assets.py)**
   so every Airbyte stream becomes a Dagster SDA without
   hand-defining `@asset` per stream. The wrapper installs the
   `vendor:<service>` Dagster concurrency pool and the rate-limit
   sensor preflight.

## Where Changes Go

- New connector: subclass
  [`RateLimitedHttpStream`](src/aqp_ingest_cdk/streams.py) under
  [`connectors/<vendor>/<stream>.py`](connectors/) and register
  via the standard Airbyte CDK source. Add a YAML manifest under
  [`marketplace/seed/`](marketplace/seed/) so the Phase 5 catalog
  surface picks it up. Tests mirror the path under [`tests/`](tests/).
- New `aqp_ingest_cdk` extension: edit
  [`src/aqp_ingest_cdk/`](src/aqp_ingest_cdk/) and re-export from
  the package `__init__.py`.
- New Airbyte HelmRelease tweak: edit
  [`../aqp_platform/deployments/kubernetes/base-services/airbyte/`](../aqp_platform/deployments/kubernetes/base-services/airbyte/).
- New REST surface: extend
  [`api/routes/`](api/routes/) and mount in the monolith's FastAPI
  app.
- Persistence models for `airbyte_connections` /
  `airbyte_sync_runs` stay in the monolith ORM at
  [`../aqp/persistence/models_airbyte.py`](../aqp/persistence/models_airbyte.py)
  — this package depends on those rows being there.

## Dependency rules

- This package depends on `aqp_ratelimit` for the
  `RateLimitedHttpStream` base + `get_ratelimit_client`.
- This package depends on the monolith for:
  `iceberg_catalog.append_arrow` (rule 3),
  `CredentialResolver`, `BrokerCredentialStore`,
  `LedgerWriter`, `_progress.emit`, `MetadataCache`,
  `LineageBus`, ORM models. No reverse dependency.

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
```
