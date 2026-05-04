# Entity Relationship Diagram

> Pair with [docs/data-dictionary.md](data-dictionary.md) (column-level
> detail) and [docs/domain-model.md](domain-model.md) (narrative).
> Doc map: [docs/index.md](index.md).

The Postgres schema has ~110 ORM classes spread across 11 model files
under [aqp/persistence/](../aqp/persistence/). One mega-ERD would be
unreadable, so this doc breaks the schema into focused diagrams by
domain. The final section is a global FK-only map showing only the
cross-domain joins.

Each per-domain ERD lists table names with the primary key (`PK`) and a
short subset of columns. For full column lists, see
[data-dictionary.md](data-dictionary.md).

## Global FK map

Cross-domain edges only — pick a starting table and trace where it
fans out.

```mermaid
erDiagram
    instruments ||--o{ instrument_equity : "polymorphic"
    instruments ||--o{ instrument_option : "polymorphic"
    instruments ||--o{ instrument_future : "polymorphic"
    instruments ||--o{ data_links : "instrument_id"
    instruments ||--o{ corporate_events : "vt_symbol"
    instruments ||--o{ news_items : "vt_symbol"
    issuers ||--o{ instruments : "issuer_id"
    issuers ||--o{ financial_statements : "issuer_id"

    data_sources ||--o{ datasets : "provider"
    dataset_catalogs ||--o{ dataset_versions : "catalog_id"
    dataset_versions ||--o{ data_links : "dataset_version_id"
    dataset_versions ||--o{ model_versions : "dataset_version_id"
    dataset_versions ||--o{ split_plans : "dataset_version_id"
    split_plans ||--o{ split_artifacts : "plan_id"

    strategies ||--o{ strategy_versions : "strategy_id"
    strategies ||--o{ backtest_runs : "strategy_id"
    backtest_runs ||--o{ orders : "backtest_id"
    backtest_runs ||--o{ fills : "backtest_id"
    backtest_runs ||--o{ signals : "backtest_id"
    backtest_runs ||--o{ ledger_entries : "backtest_id"

    sessions ||--o{ chat_messages : "session_id"
    sessions ||--o{ agent_runs : "session_id"
    crew_runs ||--o{ agent_decisions : "crew_run_id"
    agent_decisions ||--o{ debate_turns : "decision_id"
    backtest_runs ||--o{ agent_backtests : "backtest_id"
    agent_judge_reports ||--o{ agent_replay_runs : "judge_id"

    feature_sets ||--o{ feature_set_versions : "feature_set_id"
    feature_sets ||--o{ feature_set_usages : "feature_set_id"
```

## Core / Instruments

Joined-table inheritance. Every concrete instrument subclass shares the
parent `instruments` row and adds shape-specific columns in its own
table keyed on `instruments.id`. The discriminator is
`instruments.instrument_class`.

```mermaid
erDiagram
    instruments {
        uuid id PK
        string vt_symbol "AAPL.NASDAQ"
        string ticker
        string exchange
        string asset_class
        string security_type
        string instrument_class "discriminator"
        uuid issuer_id FK
        json identifiers
    }
    instrument_equity {
        uuid id PK_FK
        string isin
        string cusip
        string figi
        string lei
        string gics_sector
        float shares_outstanding
    }
    instrument_etf {
        uuid id PK_FK
        date inception_date
        float aum
        float expense_ratio
        bool is_leveraged
    }
    instrument_option {
        uuid id PK_FK
        string underlying
        float strike
        date expiry
        string kind "call|put"
        string style "european|american"
    }
    instrument_future {
        uuid id PK_FK
        string underlying
        date expiry
        float contract_size
        string cycle
    }
    instrument_fx_pair {
        uuid id PK_FK
        string base_currency
        string quote_currency
        float pip_size
    }
    instrument_crypto {
        uuid id PK_FK
        string subtype
        string chain
        string contract_address
        float max_leverage
    }
    instrument_index {
        uuid id PK_FK
        string administrator
        int constituent_count
    }
    instrument_bond {
        uuid id PK_FK
        float coupon
        date maturity
        string rating_sp
    }
    instrument_cfd {
        uuid id PK_FK
        string underlying
        float margin_rate
    }
    instrument_commodity {
        uuid id PK_FK
        string grade
        string unit_of_measure
    }
    instrument_synthetic {
        uuid id PK_FK
        json legs
        json leg_weights
    }
    instrument_betting {
        uuid id PK_FK
        string event_name
        string market_type
    }
    instrument_tokenized_asset {
        uuid id PK_FK
        string chain
        string contract_address
        string token_standard
    }

    instruments ||--o| instrument_equity : "spot"
    instruments ||--o| instrument_etf : "etf"
    instruments ||--o| instrument_option : "option"
    instruments ||--o| instrument_future : "future"
    instruments ||--o| instrument_fx_pair : "fx_pair"
    instruments ||--o| instrument_crypto : "crypto_token"
    instruments ||--o| instrument_index : "index"
    instruments ||--o| instrument_bond : "bond"
    instruments ||--o| instrument_cfd : "cfd"
    instruments ||--o| instrument_commodity : "spot_commodity"
    instruments ||--o| instrument_synthetic : "synthetic"
    instruments ||--o| instrument_betting : "betting"
    instruments ||--o| instrument_tokenized_asset : "nft"
```

## Market data lineage + Iceberg catalog

How AQP tracks every dataset that flows into Iceberg. The
`iceberg_identifier` column on `dataset_catalogs` was added in
[alembic/versions/0011_iceberg_catalog_columns.py](../alembic/versions/0011_iceberg_catalog_columns.py).

```mermaid
erDiagram
    data_sources {
        uuid id PK
        string name "yfinance|alpaca|cfpb"
        string kind "rest|csv|parquet"
        string base_url
        json meta
    }
    dataset_catalogs {
        uuid id PK
        string name
        string provider
        string domain "market.bars|cfpb.hmda"
        string frequency
        string storage_uri
        string iceberg_identifier "aqp_cfpb.hmda_lar"
        string load_mode "managed|external"
        json llm_annotations
        json column_docs
        json tags
    }
    dataset_versions {
        uuid id PK
        uuid catalog_id FK
        int version
        string status "active|superseded"
        datetime as_of
        datetime start_time
        datetime end_time
        int row_count
        int symbol_count
        string dataset_hash
        string materialization_uri
    }
    data_links {
        uuid id PK
        uuid dataset_version_id FK
        uuid source_id FK
        uuid instrument_id FK
        string entity_kind "instrument|series"
        string entity_id
        datetime coverage_start
        datetime coverage_end
        int row_count
    }
    identifier_links {
        uuid id PK
        uuid instrument_id FK
        uuid source_id FK
        string identifier_kind
        string identifier_value
    }

    dataset_catalogs ||--o{ dataset_versions : "catalog_id"
    dataset_versions ||--o{ data_links : "dataset_version_id"
    data_sources ||--o{ data_links : "source_id"
    instruments ||--o{ data_links : "instrument_id"
    data_sources ||--o{ identifier_links : "source_id"
    instruments ||--o{ identifier_links : "instrument_id"
```

## Agentic + ML

Strategies, backtests, agent crews, ML deployments, and feature sets.

```mermaid
erDiagram
    strategies {
        uuid id PK
        string name
        int version
        text config_yaml
        string status "draft|backtesting|paper|live|retired"
    }
    strategy_versions {
        uuid id PK
        uuid strategy_id FK
        text config_yaml
        json meta
    }
    backtest_runs {
        uuid id PK
        uuid strategy_id FK
        string task_id
        string status
        datetime start
        datetime end
        float sharpe
        float sortino
        float max_drawdown
        string mlflow_run_id
        string dataset_hash
        uuid model_version_id FK
        uuid ml_experiment_run_id FK
        uuid experiment_plan_id FK
        uuid model_deployment_id FK
    }
    agent_runs {
        uuid id PK
        uuid session_id FK
        string crew_name
        string status
    }
    crew_runs {
        uuid id PK
        uuid agent_run_id FK
        string preset
        json config
    }
    agent_decisions {
        uuid id PK
        uuid backtest_id FK
        uuid strategy_id FK
        uuid crew_run_id FK
        string action "long|short|flat"
        float confidence
        text rationale
    }
    debate_turns {
        uuid id PK
        uuid crew_run_id FK
        uuid decision_id FK
        string role
        text content
    }
    agent_backtests {
        uuid id PK
        uuid backtest_id FK
        json crew_metrics
    }
    agent_judge_reports {
        uuid id PK
        uuid backtest_id FK
        text summary
        json scores
    }
    agent_replay_runs {
        uuid id PK
        uuid backtest_id FK
        uuid judge_id FK
        json replay_metrics
    }
    feature_sets {
        uuid id PK
        string name
        string kind "composite|ml4t|qlib"
        json specs
        int default_lookback_days
    }
    feature_set_versions {
        uuid id PK
        uuid feature_set_id FK
        string content_hash
    }
    model_versions {
        uuid id PK
        uuid dataset_version_id FK
        uuid split_plan_id FK
        string model_class
        json hyperparams
        string mlflow_run_id
    }
    model_deployments {
        uuid id PK
        uuid model_version_id FK
        string status "active|retired"
        json runtime_meta
    }

    strategies ||--o{ strategy_versions : "strategy_id"
    strategies ||--o{ backtest_runs : "strategy_id"
    backtest_runs ||--o{ agent_decisions : "backtest_id"
    backtest_runs ||--o{ agent_backtests : "backtest_id"
    backtest_runs ||--o{ agent_judge_reports : "backtest_id"
    backtest_runs ||--o{ agent_replay_runs : "backtest_id"
    crew_runs ||--o{ agent_decisions : "crew_run_id"
    agent_decisions ||--o{ debate_turns : "decision_id"
    feature_sets ||--o{ feature_set_versions : "feature_set_id"
    model_versions ||--o{ model_deployments : "model_version_id"
```

## Ledger (signals / orders / fills / entries)

Every signal, order, fill, and free-form audit entry written by
[`LedgerWriter`](../aqp/persistence/ledger.py).

```mermaid
erDiagram
    signals {
        uuid id PK
        uuid strategy_id FK
        uuid backtest_id FK
        string vt_symbol
        string direction "long|short|net"
        float strength
        float confidence
        text rationale
    }
    orders {
        uuid id PK
        uuid backtest_id FK
        uuid strategy_id FK
        string vt_symbol
        string side "buy|sell"
        string order_type "market|limit|stop"
        float quantity
        float price
        string status
    }
    fills {
        uuid id PK
        uuid order_id FK
        float quantity
        float price
        datetime ts
    }
    ledger_entries {
        uuid id PK
        uuid backtest_id FK
        uuid strategy_id FK
        string entry_type "SIGNAL|ORDER|FILL|RISK|AUDIT"
        string level "info|warn|error"
        text message
        json payload
    }

    strategies ||--o{ signals : "strategy_id"
    backtest_runs ||--o{ signals : "backtest_id"
    strategies ||--o{ orders : "strategy_id"
    backtest_runs ||--o{ orders : "backtest_id"
    orders ||--o{ fills : "order_id"
    backtest_runs ||--o{ ledger_entries : "backtest_id"
```

## News / Events / Fundamentals

```mermaid
erDiagram
    news_items {
        uuid id PK
        string url
        string source
        datetime published_at
        text headline
        text body
    }
    news_item_entities {
        uuid id PK
        uuid news_item_id FK
        string vt_symbol
        string entity_kind "instrument|issuer|theme"
    }
    news_sentiments {
        uuid id PK
        uuid news_item_id FK
        string scorer "finbert|fingpt"
        float polarity
        float confidence
    }
    corporate_events {
        uuid id PK
        string vt_symbol
        string event_type "earnings|split|dividend|merger|ipo"
        datetime event_time
        json payload
    }
    earnings_event_rows {
        uuid id PK
        uuid event_id FK
        float eps_actual
        float eps_estimate
        float revenue_actual
    }
    dividend_event_rows {
        uuid id PK
        uuid event_id FK
        float amount
        date ex_date
        date pay_date
    }
    split_event_rows {
        uuid id PK
        uuid event_id FK
        float ratio
    }
    analyst_estimates {
        uuid id PK
        string vt_symbol
        string analyst
        float target_price
    }
    financial_statements {
        uuid id PK
        uuid issuer_id FK
        string period "Q|FY"
        date period_end
        json data
    }
    financial_ratios {
        uuid id PK
        uuid issuer_id FK
        date period_end
        float pe
        float pb
        float roe
    }
    earnings_call_transcripts {
        uuid id PK
        uuid issuer_id FK
        date call_date
        text content
    }

    news_items ||--o{ news_item_entities : "news_item_id"
    news_items ||--o{ news_sentiments : "news_item_id"
    corporate_events ||--o{ earnings_event_rows : "event_id"
    corporate_events ||--o{ dividend_event_rows : "event_id"
    corporate_events ||--o{ split_event_rows : "event_id"
    issuers ||--o{ financial_statements : "issuer_id"
    issuers ||--o{ financial_ratios : "issuer_id"
    issuers ||--o{ earnings_call_transcripts : "issuer_id"
```

## Macro / FRED / GDelt

```mermaid
erDiagram
    economic_series {
        uuid id PK
        string series_id "FRED:GDP"
        string title
        string frequency
        string units
        string source
    }
    economic_observations {
        uuid id PK
        uuid series_id FK
        date observation_date
        float value
    }
    fred_series {
        uuid id PK
        string series_id "GDP"
        string title
        string units
        string frequency
    }
    treasury_rates {
        uuid id PK
        date date
        float rate_3m
        float rate_2y
        float rate_10y
        float rate_30y
    }
    yield_curves {
        uuid id PK
        date date
        json tenors
    }
    cot_reports {
        uuid id PK
        date report_date
        string instrument
        json positions
    }
    sec_filings {
        uuid id PK
        uuid instrument_id FK
        uuid source_id FK
        string accession
        string form
        date filing_date
    }
    gdelt_mentions {
        uuid id PK
        uuid instrument_id FK
        uuid source_id FK
        datetime mention_time
        json gkg_payload
    }

    economic_series ||--o{ economic_observations : "series_id"
    instruments ||--o{ sec_filings : "instrument_id"
    instruments ||--o{ gdelt_mentions : "instrument_id"
    data_sources ||--o{ sec_filings : "source_id"
    data_sources ||--o{ gdelt_mentions : "source_id"
```

## Entities / Issuers / Ownership

```mermaid
erDiagram
    issuers {
        uuid id PK
        string name
        string lei
        string country
        string entity_kind "company|government|fund"
    }
    government_entities {
        uuid id PK_FK
        string country_code
        string level
    }
    funds {
        uuid id PK_FK
        string fund_family
        string fund_type
    }
    sectors {
        uuid id PK
        string code
        string name
    }
    industries {
        uuid id PK
        string code
        string name
        uuid sector_id FK
    }
    industry_classifications {
        uuid id PK
        uuid issuer_id FK
        uuid industry_id FK
        date as_of
    }
    entity_relationships {
        uuid id PK
        uuid parent_id FK
        uuid child_id FK
        string kind "subsidiary|owner|board"
    }
    locations {
        uuid id PK
        uuid issuer_id FK
        string country
        string city
    }
    key_executives {
        uuid id PK
        uuid issuer_id FK
        string name
        string title
    }
    insider_transactions {
        uuid id PK
        string vt_symbol
        string insider_name
        date transaction_date
        float quantity
    }
    institutional_holdings {
        uuid id PK
        string vt_symbol
        string holder_name
        date as_of
        float quantity
    }
    form_13f_holdings {
        uuid id PK
        string filer_cik
        string vt_symbol
        date period_end
    }
    short_interest {
        uuid id PK
        string vt_symbol
        date settlement_date
        float short_interest
    }
    politician_trades {
        uuid id PK
        string politician
        string vt_symbol
        date trade_date
        float amount
    }

    issuers ||--o| government_entities : "subclass"
    issuers ||--o| funds : "subclass"
    issuers ||--o{ industry_classifications : "issuer_id"
    sectors ||--o{ industries : "sector_id"
    industries ||--o{ industry_classifications : "industry_id"
    issuers ||--o{ entity_relationships : "parent_id"
    issuers ||--o{ locations : "issuer_id"
    issuers ||--o{ key_executives : "issuer_id"
```

## Taxonomy

Free-form tagging for issuers, instruments, and themes.

```mermaid
erDiagram
    taxonomy_schemes {
        uuid id PK
        string name "GICS|SASB|theme"
    }
    taxonomy_nodes {
        uuid id PK
        uuid scheme_id FK
        uuid parent_id FK
        string code
        string label
    }
    entity_tags {
        uuid id PK
        uuid node_id FK
        string entity_kind "issuer|instrument"
        string entity_id
    }
    entity_crosswalks {
        uuid id PK
        string from_kind
        string from_id
        string to_kind
        string to_id
    }

    taxonomy_schemes ||--o{ taxonomy_nodes : "scheme_id"
    taxonomy_nodes ||--o{ taxonomy_nodes : "parent_id"
    taxonomy_nodes ||--o{ entity_tags : "node_id"
```

## Sessions / Chat / Optimization

The conversational + experimentation layer.

```mermaid
erDiagram
    sessions {
        uuid id PK
        string user
        string title
        json meta
    }
    chat_messages {
        uuid id PK
        uuid session_id FK
        string role "user|assistant|agent|tool"
        text content
    }
    optimization_runs {
        uuid id PK
        uuid strategy_id FK
        json search_space
        string status
    }
    optimization_trials {
        uuid id PK
        uuid run_id FK
        uuid backtest_id FK
        json params
        float objective
    }
    paper_trading_runs {
        uuid id PK
        uuid strategy_id FK
        string status
        datetime started_at
        datetime stopped_at
    }
    rl_episodes {
        uuid id PK
        string env_id
        int episode_id
        float reward
    }

    sessions ||--o{ chat_messages : "session_id"
    sessions ||--o{ agent_runs : "session_id"
    strategies ||--o{ optimization_runs : "strategy_id"
    optimization_runs ||--o{ optimization_trials : "run_id"
    strategies ||--o{ paper_trading_runs : "strategy_id"
```

## Bots

Tables introduced by the Bot Entity Refactor (Alembic
[`0020_bots`](../alembic/versions/0020_bots.py)).

```mermaid
erDiagram
    PROJECTS ||--o{ BOTS : "owns"
    BOTS ||--o{ BOT_VERSIONS : "snapshots"
    BOTS ||--o{ BOT_DEPLOYMENTS : "runs"
    BOT_VERSIONS ||--o{ BOT_DEPLOYMENTS : "produces"

    BOTS {
        string id PK
        string project_id FK
        string slug
        string kind
        string name
        text description
        int current_version
        text spec_yaml
        string status
        json annotations
    }
    BOT_VERSIONS {
        string id PK
        string bot_id FK
        int version
        string spec_hash
        json payload
        text notes
        string created_by
    }
    BOT_DEPLOYMENTS {
        string id PK
        string bot_id FK
        string version_id FK
        string target
        string task_id
        string status
        text manifest_yaml
        json result_summary
        text error
    }
```

- `(project_id, slug)` is unique on `bots`.
- `(bot_id, spec_hash)` is unique on `bot_versions` (immutable snapshots).
- `bot_deployments.target` is one of `paper_session` / `kubernetes` /
  `backtest_only` / `chat` / `backtest`.

## Data layer expansion (sinks, producers, streaming links)

Tables introduced by the Data Pipelines Hub work (Alembic
[`0024_data_layer_expansion`](../alembic/versions/0024_data_layer_expansion.py)).
All four tables use `ProjectScopedMixin`.

```mermaid
erDiagram
    PROJECTS ||--o{ SINKS : "owns"
    SINKS ||--o{ SINK_VERSIONS : "snapshots"
    PROJECTS ||--o{ MARKET_DATA_PRODUCERS : "owns"
    DATASET_CATALOGS ||--o{ STREAMING_DATASET_LINKS : "linked"
    PIPELINE_MANIFESTS ||--o{ DATASET_PIPELINE_CONFIGS : "binds"

    SINKS {
        string id PK
        string project_id FK
        string name
        string kind
        string display_name
        json config_json
        json tags
        bool requires_manifest_node
        int current_version
        bool enabled
    }
    SINK_VERSIONS {
        string id PK
        string sink_id FK
        int version
        string spec_hash
        json payload
        text notes
    }
    MARKET_DATA_PRODUCERS {
        string id PK
        string project_id FK
        string name
        string kind
        string runtime
        string deployment_namespace
        string deployment_name
        json topics
        int desired_replicas
        int current_replicas
        string last_status
    }
    STREAMING_DATASET_LINKS {
        string id PK
        string dataset_catalog_id FK
        string kind
        string target_ref
        string cluster_ref
        string direction
        json metadata_json
        bool enabled
    }
```

Notes:

- `(project_id, name)` is unique on `sinks` and `market_data_producers`.
- `(sink_id, spec_hash)` and `(sink_id, version)` are unique on
  `sink_versions` (mirrors the `bot_versions` pattern).
- `(dataset_catalog_id, kind, target_ref, direction)` is unique on
  `streaming_dataset_links` so the
  [refresh_links](../aqp/tasks/streaming_link_tasks.py) task can be
  re-run idempotently.

## ML alpha-backtest linkage (Alembic 0025)

```mermaid
erDiagram
    ml_experiment_runs ||--o| ml_alpha_backtest_runs : "ml_experiment_run_id"
    backtest_runs ||--o| ml_alpha_backtest_runs : "backtest_run_id"
    model_versions ||--o| ml_alpha_backtest_runs : "model_version_id"
    model_deployments ||--o| ml_alpha_backtest_runs : "model_deployment_id"
    experiment_plans ||--o| ml_alpha_backtest_runs : "experiment_plan_id"
    ml_alpha_backtest_runs ||--o{ ml_prediction_audit : "alpha_backtest_run_id"

    ml_alpha_backtest_runs {
        uuid id PK
        string task_id
        string run_name
        string status
        uuid ml_experiment_run_id FK
        uuid backtest_run_id FK
        uuid model_version_id FK
        uuid model_deployment_id FK
        uuid experiment_plan_id FK
        string mlflow_run_id
        json ml_metrics
        json trading_metrics
        json combined_metrics
        json attribution
        datetime started_at
        datetime completed_at
    }
    ml_prediction_audit {
        uuid id PK
        uuid alpha_backtest_run_id FK
        string vt_symbol
        datetime ts
        float prediction
        float label
        float position_after
        float pnl_after_bar
    }
```

The four new FKs on `backtest_runs` (added by Alembic 0025) close the
loop from a backtest result back to the trained model that produced
its alpha:

- `model_version_id` — the registered `ModelVersion` row.
- `ml_experiment_run_id` — the `MLExperimentRun` that trained it.
- `experiment_plan_id` — the `ExperimentPlan` lineage row.
- `model_deployment_id` — the `ModelDeployment` used to wire the
  model into the strategy via `DeployedModelAlpha`.

## Adding a new model

When you add a new ORM class:

1. Add the class to the appropriate `aqp/persistence/models_*.py`
   (or `models.py` for cross-domain things).
2. Add an Alembic migration (`alembic revision --autogenerate -m
   "add foo"`). **Never edit a shipped migration.**
3. Update [docs/data-dictionary.md](data-dictionary.md) with the new
   table's columns.
4. Add the table to the relevant per-domain ERD above (or open a new
   one if it's a new domain).
5. If it has FKs into other domains, add those edges to the global FK
   map at the top of this file.
