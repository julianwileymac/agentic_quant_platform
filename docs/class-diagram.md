# Class Diagrams

> Pair with [docs/erd.md](erd.md) (database schema) and
> [docs/architecture.md](architecture.md) (system view).
> Doc map: [docs/index.md](index.md).

Hand-authored mermaid `classDiagram` blocks for the five hierarchies AI
coders most often need to navigate. Every diagram cites the canonical
file so you can jump from the diagram into the code in one click.

## 1. Symbol + core enums

The atom that flows through every data feed, strategy, and broker.
Defined in [aqp/core/types.py](../aqp/core/types.py).

```mermaid
classDiagram
    class Symbol {
        +str ticker
        +Exchange exchange
        +AssetClass asset_class
        +SecurityType security_type
        +str vt_symbol
        +parse(s) Symbol
        +format() str
        +equity(ticker, exchange) Symbol
        +crypto(base, quote, venue) Symbol
        +option(underlying, ...) Symbol
    }
    class Exchange {
        <<StrEnum>>
        NASDAQ
        NYSE
        ARCA
        BATS
        CBOE
        CME
        LSE
        BINANCE
        COINBASE
        SIM
        LOCAL
    }
    class AssetClass {
        <<StrEnum>>
        EQUITY
        CRYPTO
        FX
        FUTURE
        OPTION
        INDEX
        COMMODITY
        BOND
        BASE
    }
    class SecurityType {
        <<StrEnum>>
        EQUITY
        OPTION
        FUTURE
        FUTURE_OPTION
        FOREX
        CFD
        CRYPTO
        CRYPTO_FUTURE
        INDEX
        INDEX_OPTION
        COMMODITY
    }
    class Resolution {
        <<StrEnum>>
        Tick
        Second
        Minute
        Hour
        Daily
    }
    class TickType {
        <<StrEnum>>
        Trade
        Quote
        OpenInterest
    }
    class SubscriptionDataConfig {
        +Symbol symbol
        +Resolution resolution
        +TickType tick_type
        +DataNormalizationMode mode
    }
    class BarData {
        +Symbol symbol
        +datetime timestamp
        +Decimal open
        +Decimal high
        +Decimal low
        +Decimal close
        +int volume
    }
    class QuoteBar
    class TradeBar
    class TickData

    Symbol --> Exchange : "uses"
    Symbol --> AssetClass : "uses"
    Symbol --> SecurityType : "uses"
    SubscriptionDataConfig --> Symbol
    SubscriptionDataConfig --> Resolution
    SubscriptionDataConfig --> TickType
    BarData --> Symbol
    QuoteBar --|> BarData
    TradeBar --|> BarData
    TickData --> Symbol
```

**Key invariants**:

- `Symbol` is hashable + frozen. Round-trip via
  `Symbol.parse(symbol.format())` is the identity.
- `vt_symbol` is always `f"{ticker}.{exchange}"` (vnpy convention).
- Concrete instrument shapes (option chains, future contracts) live
  alongside `Symbol` as additional fields, not separate classes.

## 2. LLM provider registry

The router from [aqp/llm/providers/router.py](../aqp/llm/providers/router.py)
dispatches every LLM call through LiteLLM. Adding a provider is a
single dict entry in
[aqp/llm/providers/catalog.py](../aqp/llm/providers/catalog.py).

```mermaid
classDiagram
    class ProviderSpec {
        <<dataclass>>
        +str slug
        +str litellm_prefix
        +str env_key
        +str settings_attr
        +str base_url_attr
        +str default_deep_model
        +str default_quick_model
        +bool requires_api_key
    }
    class LLMProvider {
        <<abstract>>
        +ProviderSpec spec
        +model_string(model) str*
        +api_key() str*
        +base_url() str*
        +default_model(tier) str
    }
    class _DefaultProvider {
        +model_string(model) str
        +api_key() str
        +base_url() str
    }
    class LLMResult {
        <<dataclass>>
        +str content
        +str model
        +str provider
        +int prompt_tokens
        +int completion_tokens
        +float cost_usd
        +Any raw
    }
    class router_complete {
        <<function>>
        +complete(provider, model, prompt, ...) LLMResult
    }
    class PROVIDERS {
        <<registry>>
        openai
        anthropic
        google
        xai
        deepseek
        groq
        openrouter
        ollama
        vllm
    }

    LLMProvider <|-- _DefaultProvider
    _DefaultProvider --> ProviderSpec
    PROVIDERS --> ProviderSpec : "values"
    router_complete --> LLMProvider : "get_provider(slug)"
    router_complete --> LLMResult : "returns"
```

**Conventions**:

- Always call via `router_complete(provider=..., model=..., ...)`.
- Tier (`deep`/`quick`) routing happens via `settings.provider_for_tier`
  + `provider.default_model(tier)`.
- The control plane in [aqp/runtime/control_plane.py](../aqp/runtime/control_plane.py)
  can override `ollama_host` / `vllm_base_url` at runtime.

## 3. Strategy hierarchy

AQP follows the Lean 5-stage pattern (Universe → Alpha → Portfolio →
Risk → Execution). Concrete strategies are factory-instantiated from
config via the `class`/`module_path`/`kwargs` registry pattern.

```mermaid
classDiagram
    class IStrategy {
        <<interface>>
        +on_bar(bar, context) Iterator~OrderRequest~
        +on_order_update(order) None
    }
    class IUniverseSelectionModel {
        <<interface>>
        +select(timestamp, context) list~Symbol~
    }
    class IAlphaModel {
        <<interface>>
        +generate_signals(history, universe, context) list~Signal~
    }
    class IPortfolioConstructionModel {
        <<interface>>
        +construct(signals, context) list~PortfolioTarget~
    }
    class IRiskManagementModel {
        <<interface>>
        +evaluate(targets, context) list~PortfolioTarget~
    }
    class IExecutionModel {
        <<interface>>
        +execute(targets, context) list~OrderRequest~
    }
    class FrameworkAlgorithm {
        +IUniverseSelectionModel universe_model
        +IAlphaModel alpha_model
        +IPortfolioConstructionModel portfolio_model
        +IRiskManagementModel risk_model
        +IExecutionModel execution_model
        +int rebalance_every
        +on_bar(bar, context) Iterator
    }
    class MeanReversionAlpha
    class MomentumAlpha
    class MLAlphaStrategy
    class MLSelectorAlpha
    class EnsembleAlpha {
        +list~IAlphaModel~ alphas
        +list~float~ weights
    }
    class DeployedModelAlpha {
        +str deployment_id
    }
    class BlackLittermanPortfolio
    class HRPPortfolio
    class MeanVariancePortfolio
    class RiskParityPortfolio
    class TwapExecution
    class VwapExecution

    IStrategy <|.. FrameworkAlgorithm
    IAlphaModel <|.. MeanReversionAlpha
    IAlphaModel <|.. MomentumAlpha
    IAlphaModel <|.. MLAlphaStrategy
    IAlphaModel <|.. MLSelectorAlpha
    IAlphaModel <|.. EnsembleAlpha
    IAlphaModel <|.. DeployedModelAlpha
    IPortfolioConstructionModel <|.. BlackLittermanPortfolio
    IPortfolioConstructionModel <|.. HRPPortfolio
    IPortfolioConstructionModel <|.. MeanVariancePortfolio
    IPortfolioConstructionModel <|.. RiskParityPortfolio
    IExecutionModel <|.. TwapExecution
    IExecutionModel <|.. VwapExecution
    FrameworkAlgorithm o-- IUniverseSelectionModel
    FrameworkAlgorithm o-- IAlphaModel
    FrameworkAlgorithm o-- IPortfolioConstructionModel
    FrameworkAlgorithm o-- IRiskManagementModel
    FrameworkAlgorithm o-- IExecutionModel
    EnsembleAlpha o-- "many" IAlphaModel
```

The interfaces are in [aqp/core/interfaces.py](../aqp/core/interfaces.py);
concrete alphas in [aqp/strategies/](../aqp/strategies/) (one file per
alpha). See [docs/factor-research.md](factor-research.md) for the
authoring guide.

## 4. Backtest + paper + live (IBrokerage / IDataQueueHandler)

The same strategy runs unchanged across backtest, paper, and live —
the engines differ in how they implement the broker + data-queue
contract, not in how they call the strategy.

```mermaid
classDiagram
    class IBrokerage {
        <<interface>>
        +submit_order(order) OrderTicket
        +cancel_order(ticket) bool
        +get_positions() list~SecurityHolding~
        +get_cashbook() CashBook
        +on_order_event(callback) None
    }
    class IDataQueueHandler {
        <<interface>>
        +subscribe(config) None
        +unsubscribe(config) None
        +get_next_ticks() Iterable~Tick~
    }
    class IHistoryProvider {
        <<interface>>
        +get_bars(symbol, start, end, resolution) DataFrame
    }
    class BacktestEngine {
        +IStrategy strategy
        +IDataQueueHandler data
        +IBrokerage brokerage
        +run(start, end) BacktestResult
    }
    class VectorbtEngine {
        +run(start, end) BacktestResult
    }
    class LocalSimulationEngine
    class PaperTradingEngine
    class WalkForwardEngine
    class MonteCarloEngine
    class BrokerSim {
        +decimal cash
        +dict positions
    }
    class AlpacaBrokerage
    class IbkrBrokerage
    class TradierBrokerage
    class DuckDBHistoryProvider
    class KafkaDataFeed

    IBrokerage <|.. BrokerSim
    IBrokerage <|.. AlpacaBrokerage
    IBrokerage <|.. IbkrBrokerage
    IBrokerage <|.. TradierBrokerage
    IDataQueueHandler <|.. KafkaDataFeed
    IHistoryProvider <|.. DuckDBHistoryProvider
    BacktestEngine <|-- VectorbtEngine
    BacktestEngine <|-- LocalSimulationEngine
    BacktestEngine <|-- PaperTradingEngine
    BacktestEngine <|-- WalkForwardEngine
    BacktestEngine <|-- MonteCarloEngine
    BacktestEngine o-- IBrokerage
    BacktestEngine o-- IDataQueueHandler
```

Files of interest:

- [aqp/backtest/engine.py](../aqp/backtest/engine.py) — base engine
- [aqp/backtest/vectorbt_engine.py](../aqp/backtest/vectorbt_engine.py)
- [aqp/backtest/broker_sim.py](../aqp/backtest/broker_sim.py) — brokerage
  simulator used by all non-live engines
- [aqp/trading/](../aqp/trading/) — concrete `IBrokerage`
  implementations for paper + live
- [aqp/streaming/](../aqp/streaming/) — Kafka and IBKR feed handlers

See [docs/backtest-engines.md](backtest-engines.md) for the full
engine matrix, [docs/paper-trading.md](paper-trading.md) for the
session lifecycle.

## 5. Generic ingestion pipeline

Discovery → Director → Materialise → Verify → Annotate. The
dataclasses below are the canonical contract between stages.

```mermaid
classDiagram
    class DiscoveredMember {
        <<dataclass>>
        +str path
        +str archive_path
        +str format
        +str delimiter
        +int size_bytes
        +str subdir
        +float outer_mtime
    }
    class DiscoveredDataset {
        <<dataclass>>
        +str family
        +list~DiscoveredMember~ members
        +int total_bytes
        +list~str~ sample_columns
        +list~str~ notes
        +list inventory_extra
    }
    class IngestionPlan {
        <<dataclass>>
        +str source_path
        +str namespace
        +list~PlannedDataset~ datasets
        +list skipped_assets
        +str director_raw
        +bool director_used
        +str director_error
    }
    class PlannedDataset {
        <<dataclass>>
        +str family
        +bool include
        +str target_namespace
        +str target_table
        +int expected_min_rows
        +str domain_hint
        +list~str~ member_paths
        +list~str~ skip_member_paths
        +str notes
        +iceberg_identifier() str
    }
    class VerifierVerdict {
        <<dataclass>>
        +str verdict
        +str reason
        +dict retry_with
        +str raw
        +str error
    }
    class MaterializeResult {
        <<dataclass>>
        +str iceberg_identifier
        +str table_name
        +int rows_written
        +int files_consumed
        +int files_skipped
        +bool truncated
        +list schema_fields
        +str error
    }
    class IngestionTableResult {
        <<dataclass>>
        +str family
        +str iceberg_identifier
        +int rows_written
        +bool truncated
        +dict annotation
        +dict plan
        +dict verifier
        +str error
    }
    class IngestionReport {
        <<dataclass>>
        +str source_path
        +str namespace
        +datetime started_at
        +datetime finished_at
        +int datasets_discovered
        +list~IngestionTableResult~ tables
        +list extras
        +list~str~ errors
        +dict director_plan
    }
    class IngestionPipeline {
        +ProgressCallback progress_cb
        +int max_rows_per_dataset
        +int max_files_per_dataset
        +int chunk_rows
        +bool director_enabled
        +list~str~ allowed_namespaces
        +run_path(path, namespace, annotate) IngestionReport
    }
    class AnnotationResult {
        <<dataclass>>
        +str identifier
        +str description
        +list~str~ tags
        +str domain
        +list pii_flags
        +list column_docs
        +str error
    }

    DiscoveredDataset o-- "many" DiscoveredMember
    IngestionPlan o-- "many" PlannedDataset
    IngestionPipeline ..> DiscoveredDataset : "discovery output"
    IngestionPipeline ..> IngestionPlan : "director output"
    IngestionPipeline ..> MaterializeResult : "per planned table"
    IngestionPipeline ..> VerifierVerdict : "if floor missed"
    IngestionPipeline ..> AnnotationResult : "if annotate=true"
    IngestionTableResult o-- VerifierVerdict
    IngestionTableResult o-- AnnotationResult
    IngestionReport o-- "many" IngestionTableResult
```

Files:

- [aqp/data/pipelines/discovery.py](../aqp/data/pipelines/discovery.py)
- [aqp/data/pipelines/director.py](../aqp/data/pipelines/director.py)
- [aqp/data/pipelines/materialize.py](../aqp/data/pipelines/materialize.py)
- [aqp/data/pipelines/annotate.py](../aqp/data/pipelines/annotate.py)
- [aqp/data/pipelines/runner.py](../aqp/data/pipelines/runner.py)
- [aqp/data/pipelines/extractors.py](../aqp/data/pipelines/extractors.py)

Walkthrough lives in [docs/data-catalog.md](data-catalog.md).

## 6. Bot entity (TradingBot / ResearchBot)

The Bot Entity Refactor introduced a first-class deployable unit that
aggregates universe + strategy + engine + ML + agents + RAG + metrics.
The runtime never re-implements those primitives — it composes
references and dispatches to the existing entry points.

```mermaid
classDiagram
    class BotSpec {
        <<pydantic>>
        +str name
        +str slug
        +str kind
        +UniverseRef universe
        +DataPipelineRef data_pipeline
        +dict strategy
        +dict backtest
        +list~MLDeploymentRef~ ml_models
        +list~BotAgentRef~ agents
        +list~RAGRef~ rag
        +list~MetricRef~ metrics
        +RiskSpec risk
        +DeploymentTargetSpec deployment
        +snapshot_hash() str
    }
    class BaseBot {
        <<abstract>>
        +BotSpec spec
        +str bot_id
        +str project_id
        +backtest(run_name, **overrides) dict
        +paper(run_name, **overrides) PaperTradingSession
        +deploy(target, **overrides) BotDeploymentResult
        +chat(prompt, ...) Any
        +metrics_snapshot(run_summary) dict
    }
    class TradingBot {
        +consult_agents(prompt, inputs, roles) dict
    }
    class ResearchBot {
        +chat(prompt, session_id, agent_role, inputs) dict
    }
    class BotRuntime {
        +BotSpec spec
        +str run_id
        +str task_id
        +backtest(run_name, overrides) BotRunResult
        +paper(run_name, overrides) BotRunResult
        +chat(prompt, session_id, agent_role) BotRunResult
        +deploy(target, overrides) BotRunResult
    }
    class DeploymentDispatcher {
        +deploy(bot, target, overrides) BotDeploymentResult
        +register(target) void
    }
    class DeploymentTarget {
        <<abstract>>
        +str name
        +deploy(bot, overrides) BotDeploymentResult
    }
    class PaperSessionTarget
    class BacktestOnlyTarget
    class KubernetesTarget {
        +Path manifest_root
        +bool apply
        +render_manifest(bot, overrides) str
    }

    BotSpec <.. BaseBot
    BaseBot <|-- TradingBot
    BaseBot <|-- ResearchBot
    BotRuntime ..> BaseBot
    DeploymentDispatcher --> DeploymentTarget
    DeploymentTarget <|-- PaperSessionTarget
    DeploymentTarget <|-- BacktestOnlyTarget
    DeploymentTarget <|-- KubernetesTarget
    BotRuntime ..> DeploymentDispatcher : "deploy()"
```

Files:

- [aqp/bots/spec.py](../aqp/bots/spec.py)
- [aqp/bots/base.py](../aqp/bots/base.py)
- [aqp/bots/trading_bot.py](../aqp/bots/trading_bot.py)
- [aqp/bots/research_bot.py](../aqp/bots/research_bot.py)
- [aqp/bots/runtime.py](../aqp/bots/runtime.py)
- [aqp/bots/deploy.py](../aqp/bots/deploy.py)
- [aqp/bots/registry.py](../aqp/bots/registry.py)
- [aqp/bots/cli.py](../aqp/bots/cli.py)

Walkthrough lives in [docs/bots.md](bots.md).
