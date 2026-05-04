# Data Pipelines Hub

The **Data Pipelines** submenu under **Research → Data Pipelines** is
the unified surface for everything that moves data into and around
AQP. It absorbs the existing `Data Ingest` and `Data Pipeline Editor`
pages and adds six new entries:

| Page | Route | Backed by |
| --- | --- | --- |
| **Pipelines Hub** | `/data/pipelines/hub` | `/data-control/*`, `/engine/*`, `/airbyte/*`, `/dbt/*`, `/dagster/*` |
| **Sinks** | `/data/sinks` | `/sinks` |
| **Project Datasets** | `/data/datasets/configs` | `/projects/{id}/dataset-configs` |
| **Kafka** | `/streaming/kafka` | `/streaming/kafka/*` (native + cluster-mgmt fallback) |
| **Flink** | `/streaming/flink` | `/streaming/flink/*` (native + cluster-mgmt fallback) |
| **Producers** | `/streaming/producers` | `/streaming/producers/*` |

## Sinks

The `Sinks` page is a project-scoped registry of saved sink
configurations. Each row is a [`SinkRow`](../aqp/persistence/models_sinks.py)
backed by an immutable hash-locked
[`SinkVersionRow`](../aqp/persistence/models_sinks.py) snapshot every
time the configuration changes (mirrors the `bot_versions` /
`agent_spec_versions` pattern).

The supported kinds (`/sinks/kinds`) are:

| Kind | Class | Notes |
| --- | --- | --- |
| `iceberg` | [`IcebergSink`](../aqp/data/fetchers/sinks/iceberg_sink.py) | Always goes through `iceberg_catalog.append_arrow` per AGENTS.md hard rule #3. |
| `parquet` | [`ParquetSink`](../aqp/data/fetchers/sinks/parquet_sink.py) | One file per batch in a directory. |
| `kafka` | [`KafkaSink`](../aqp/data/fetchers/sinks/kafka_sink.py) | Publishes JSON rows to a topic. |
| `chroma` | [`ChromaSink`](../aqp/data/fetchers/sinks/chroma_sink.py) | Embedded Chroma vector collection writer. |
| `profile` | [`ProfileSink`](../aqp/data/fetchers/sinks/profile_sink.py) | Computes a dataset profile for the cache. |
| `dbt_build` | [`DbtBuildSink`](../aqp/data/fetchers/sinks/dbt_sink.py) | Materialises rows as a dbt seed/source. |

`POST /sinks/{id}/materialise` resolves a saved sink into a
manifest-ready [`NodeSpec`](../aqp/data/engine/manifest.py) — bots and
pipelines reference sinks via this endpoint instead of inlining the
configuration.

## Project Datasets

`/data/datasets/configs` reads
[`DatasetPipelineConfigRow`](../aqp/persistence/models_data_control.py)
rows scoped to the active project (from
`/projects/{id}/dataset-configs`). Each row binds:

- a curated `DatasetPreset` or a custom manifest,
- one or more `Sink` ids (the rendered manifest's terminal node),
- one or more automation entries (cron schedules consumed by
  [`aqp/tasks/scheduling.py`](../aqp/tasks/scheduling.py) which
  re-merges them into Celery beat).

Use the **Setup wizard** action on a preset card to walk through the
credentials → sinks → schedule → save → trigger sequence. The wizard
is implemented as a per-preset
[`PresetWizard`](../aqp/data/dataset_presets_wizards.py) and exposed
at `GET /dataset-presets/{name}/wizard` /
`POST /dataset-presets/{name}/wizard/step`.

## Pipelines Hub

`/data/pipelines/hub` aggregates four tabs:

- **Automations** — cron schedules from `pipeline_manifests` plus
  `dataset_pipeline_configs`. Editing a cron writes through to the
  matching ORM row and refreshes Celery beat in-process.
- **Pipelines** — scheduled manifests, with one-click `run-background`.
- **Connectors** — engine source fetchers (registered via
  [`@register_node`](../aqp/data/engine/registry.py)) + Airbyte
  connections.
- **Transformations** — dbt models + transform fetchers + ML feature
  sets.

## Agentic dataset loader

The **Ask agent** tab on `/data/ingest` runs the
[`dataset_loading_assistant`](../configs/agents/dataset_loading_assistant.yaml)
spec via [`AgentRuntime`](../aqp/agents/runtime.py) (per AGENTS.md
hard rule #11/#12 — never `router_complete` directly). The agent has
seven read-only tools registered in
[`aqp.agents.tools.data_tools`](../aqp/agents/tools/data_tools.py):

| Tool | Use |
| --- | --- |
| `inspect_path` | Walk a local path / file. |
| `peek_url` | HEAD + truncated GET on a URL. |
| `lookup_dataset_preset` | Search the curated preset library. |
| `propose_pipeline_manifest` | Render a manifest dict. |
| `propose_setup_wizard` | Surface the matching source wizard. |
| `enrich_metadata_with_dbt_artifacts` | Pull column docs from `manifest.json`. |
| `summarise_airbyte_catalog` | List Airbyte connectors that match. |

The agent always returns JSON shaped
`{summary, preset_match, proposed_manifest, setup_wizard, next_actions}`;
the UI surfaces an "Accept manifest" button that writes the manifest
to `/engine/manifests`.

## Project-scoped configs

All new tables (`sinks`, `sink_versions`,
`market_data_producers`, `streaming_dataset_links`) use
[`ProjectScopedMixin`](../aqp/persistence/_tenancy_mixins.py). The
[`current_context`](../aqp/auth/deps.py) dependency injects the
active project automatically, so flipping `X-AQP-Project` in the UI
flips the visible registry without code changes.
