"""Runtime configuration via Pydantic Settings.

All knobs are loaded from environment variables (``.env``) with the ``AQP_``
prefix. Add new settings here and they become instantly available to every
service via ``from aqp.config import settings``.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AQP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- FinOps / Cloud Governance ---
    # These tags are mandatory for all cloud-deployed resources.
    # They are used for cost allocation, forecasting, and ROI analysis.
    project_tag: str = Field(default="aqp-default")
    cost_center: str = Field(default="quant-research-01")
    owner: str = Field(default="system-orchestrator")
    data_classification: str = Field(default="proprietary-alpha")

    # --- runtime ---
    env: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    # --- paths ---
    data_dir: Path = Field(default=Path("./data"))
    parquet_dir: Path = Field(default=Path("./data/parquet"))
    models_dir: Path = Field(default=Path("./data/models"))
    chroma_dir: Path = Field(default=Path("./data/chroma"))
    arctic_uri: str = Field(default="lmdb://./data/arctic")

    # --- LLM / Ollama / LiteLLM ---
    llm_provider: str = Field(default="ollama")
    llm_provider_deep: str = Field(default="")
    llm_provider_quick: str = Field(default="")
    ollama_host: str = Field(default="http://localhost:11434")
    llm_model: str = Field(default="nemotron:latest")
    llm_deep_model: str = Field(default="nemotron:latest")
    llm_quick_model: str = Field(default="llama3.2:latest")
    llm_temperature_deep: float = Field(default=0.2)
    llm_temperature_quick: float = Field(default=0.4)
    llm_context_window: int = Field(default=32768)
    llm_request_timeout: int = Field(default=120)
    # --- Data-pipeline Director (Nemotron by default).
    llm_director_provider: str = Field(default="ollama")
    llm_director_model: str = Field(default="nemotron-3-nano:30b")
    llm_director_temperature: float = Field(default=0.1)
    llm_director_max_tokens: int = Field(default=4096)
    llm_director_enabled: bool = Field(default=True)
    openai_api_key: str = Field(default="")
    openai_base_url: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    google_api_key: str = Field(default="")
    xai_api_key: str = Field(default="")
    deepseek_api_key: str = Field(default="")
    groq_api_key: str = Field(default="")
    openrouter_api_key: str = Field(default="")
    # vLLM — OpenAI-compatible HTTP API.
    vllm_base_url: str = Field(default="")
    vllm_api_key: str = Field(default="")
    vllm_default_model: str = Field(default="nemotron")

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_pubsub_url: str = Field(default="redis://localhost:6379/1")

    # --- Postgres ---
    postgres_dsn: str = Field(
        default="postgresql+psycopg2://aqp:aqp@localhost:5432/aqp",
    )
    postgres_async_dsn: str = Field(
        default="postgresql+asyncpg://aqp:aqp@localhost:5432/aqp",
    )

    # --- ChromaDB ---
    chroma_host: str = Field(default="localhost")
    chroma_port: int = Field(default=8001)
    chroma_embedding_model: str = Field(default="all-MiniLM-L6-v2")

    # --- Hierarchical RAG (Redis Stack / RediSearch) ---
    # All RAG vectors + tag indexes live in the single Redis instance
    # configured by ``redis_url``. Index keys are namespaced by
    # ``rag_redis_prefix`` so other Redis users in the cluster aren't
    # affected. The default embedder is BGE-M3 (matches the Alpha-GPT
    # paper); falls back to all-MiniLM-L6-v2 if BGE-M3 isn't installed
    # and finally to a deterministic hash embedder for hermetic tests.
    rag_redis_prefix: str = Field(default="aqp:rag")
    rag_embedder: str = Field(default="BAAI/bge-m3")
    rag_reranker: str = Field(default="BAAI/bge-reranker-base")
    rag_default_k: int = Field(default=8)
    rag_per_level_k: int = Field(default=5)
    rag_raptor_levels: int = Field(default=3)
    rag_raptor_k_max: int = Field(default=8)
    rag_audit_enabled: bool = Field(default=True)
    rag_compress_threshold: float = Field(default=0.15)
    rag_working_max: int = Field(default=64)

    # --- Agent runtime / observability ---
    agent_run_artifact_dir: Path = Field(default=Path("./data/agent_runs"))
    agent_default_max_calls: int = Field(default=20)
    agent_default_max_cost_usd: float = Field(default=2.0)
    agent_decision_log_path: Path = Field(default=Path("./data/agent_runs/decision_log.md"))

    # --- Regulatory data adapter credentials ---
    cfpb_user_agent: str = Field(default="aqp-research/0.1 (+https://github.com/)")
    cfpb_base_url: str = Field(default="https://www.consumerfinance.gov/data-research/consumer-complaints")
    cfpb_api_url: str = Field(default="https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1")
    fda_api_key: str = Field(default="")
    fda_base_url: str = Field(default="https://api.fda.gov")
    uspto_api_key: str = Field(default="")
    uspto_patentsview_url: str = Field(default="https://search.patentsview.org/api/v1")
    uspto_peds_url: str = Field(default="https://ped.uspto.gov/api")
    uspto_tsdr_url: str = Field(default="https://tsdrapi.uspto.gov/ts/cd/casestatus")

    # --- MLflow ---
    mlflow_tracking_uri: str = Field(default="http://localhost:5000")
    mlflow_experiment: str = Field(default="aqp-default")
    mlflow_registry_uri: str = Field(default="")  # "" = same as tracking URI
    mlflow_serve_host: str = Field(default="0.0.0.0")
    mlflow_serve_port: int = Field(default=5001)

    # --- Ray Serve ---
    ray_address: str = Field(default="auto")
    ray_serve_http_host: str = Field(default="0.0.0.0")
    ray_serve_http_port: int = Field(default=8000)
    ray_serve_route_prefix: str = Field(default="/aqp")

    # --- TorchServe ---
    torchserve_inference_url: str = Field(default="http://localhost:8080")
    torchserve_management_url: str = Field(default="http://localhost:8081")
    torchserve_model_store: Path = Field(default=Path("./data/torchserve/model-store"))

    # --- Sentiment / FinGPT ---
    sentiment_model: str = Field(default="yiyanghkust/finbert-tone")
    fingpt_forecaster_model: str = Field(default="")
    finrobot_default_tier: str = Field(default="deep")

    # --- Cross-repo integration ---
    agentic_assistants_api: str = Field(default="")
    minio_endpoint_url: str = Field(default="")
    minio_access_key: str = Field(default="")
    minio_secret_key: str = Field(default="")
    minio_artifacts_bucket: str = Field(default="aqp-artifacts")
    minio_datasets_bucket: str = Field(default="aqp-datasets")

    # --- FastAPI ---
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_reload: bool = Field(default=True)
    api_url: str = Field(default="http://localhost:8000")

    # --- UI ---
    ui_host: str = Field(default="0.0.0.0")
    ui_port: int = Field(default=8765)

    # --- WebUI (Next.js) ---
    webui_cors_origins: str = Field(default="")

    # --- Celery ---
    celery_concurrency: int = Field(default=4)
    celery_gpu_concurrency: int = Field(default=1)

    # --- Risk defaults ---
    risk_max_position_pct: float = Field(default=0.20)
    risk_max_daily_loss_pct: float = Field(default=0.03)
    risk_max_drawdown_pct: float = Field(default=0.15)
    risk_kill_switch_key: str = Field(default="aqp:kill_switch")

    # --- Data defaults ---
    default_universe: str = Field(
        default="SPY,AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META,JPM,JNJ",
    )
    default_start: str = Field(default="2020-01-01")
    default_end: str = Field(default="2024-12-31")

    local_data_roots: str = Field(default="")
    market_bars_provider: str = Field(default="auto")
    fundamentals_provider: str = Field(default="auto")
    universe_provider: str = Field(default="managed_snapshot")
    managed_universe_limit: int = Field(default=200)

    # --- Paper trading ---
    paper_default_heartbeat_seconds: int = Field(default=30)
    paper_state_flush_every_bars: int = Field(default=10)

    # --- Alpaca ---
    alpaca_api_key: str = Field(default="")
    alpaca_secret_key: str = Field(default="")
    alpaca_paper: bool = Field(default=True)
    alpaca_base_url: str = Field(default="")

    # --- Interactive Brokers (TWS / IB Gateway) ---
    ibkr_host: str = Field(default="127.0.0.1")
    ibkr_port: int = Field(default=7497)
    ibkr_client_id: int = Field(default=1)

    # --- Tradier ---
    tradier_token: str = Field(default="")
    tradier_base_url: str = Field(default="https://sandbox.tradier.com/v1")
    tradier_account_id: str = Field(default="")

    # --- Alpha Vantage ---
    alpha_vantage_enabled: bool = Field(default=True)
    alpha_vantage_api_key: str = Field(default="")
    alpha_vantage_api_key_file: str = Field(default="")
    alpha_vantage_base_url: str = Field(default="https://www.alphavantage.co/query")
    alpha_vantage_rpm_limit: int = Field(default=75)
    alpha_vantage_daily_limit: int = Field(default=0)
    alpha_vantage_timeout_seconds: float = Field(default=30.0)
    alpha_vantage_max_retries: int = Field(default=5)
    alpha_vantage_cache_backend: str = Field(default="memory")
    alpha_vantage_cache_max_entries: int = Field(default=512)
    alpha_vantage_rapidapi: bool = Field(default=False)
    alpha_vantage_intraday_interval: str = Field(default="1min")
    alpha_vantage_intraday_lookback_months: int = Field(default=36)
    alpha_vantage_intraday_batch_size: int = Field(default=25)
    alpha_vantage_intraday_run_guard_max_starts: int = Field(default=3)
    alpha_vantage_intraday_run_guard_window_seconds: int = Field(default=900)
    alpha_vantage_intraday_manifest_dir: Path = Field(
        default=Path("./data/alpha_vantage/intraday_components")
    )
    alpha_vantage_intraday_namespace: str = Field(default="aqp_alpha_vantage")
    alpha_vantage_intraday_table: str = Field(default="time_series_intraday")

    # --- DataHub metadata emission ---
    datahub_gms_url: str = Field(default="")
    datahub_token: str = Field(default="")
    datahub_env: str = Field(default="PROD")

    # --- OpenTelemetry ---
    otel_endpoint: str = Field(default="")
    otel_service_name: str = Field(default="aqp")
    otel_sample_ratio: float = Field(default=1.0)
    otel_protocol: str = Field(default="grpc")

    # --- Kafka ---
    kafka_bootstrap: str = Field(default="localhost:9092")
    kafka_client_id: str = Field(default="aqp")
    kafka_compression: str = Field(default="zstd")
    kafka_acks: str = Field(default="all")
    kafka_security_protocol: str = Field(default="PLAINTEXT")
    kafka_sasl_mechanism: str = Field(default="")
    kafka_sasl_username: str = Field(default="")
    kafka_sasl_password: str = Field(default="")
    kafka_topic_prefix: str = Field(default="")
    kafka_consumer_group: str = Field(default="aqp-live")

    # --- Streaming ingester ---
    stream_universe: str = Field(default="")
    stream_config_file: str = Field(default="")
    stream_market_data_type: int = Field(default=3)
    stream_scanner_interval_sec: int = Field(default=300)
    stream_scanner_enabled: bool = Field(default=False)
    stream_include_quotes: bool = Field(default=True)
    stream_include_trades: bool = Field(default=True)
    stream_include_bars: bool = Field(default=True)
    stream_metrics_port: int = Field(default=9300)
    stream_health_port: int = Field(default=9301)

    # --- Alpaca streaming ---
    alpaca_feed: str = Field(default="iex")
    news_provider: str = Field(default="yfinance")
    agentic_default_preset: str = Field(default="trader_crew_quick")
    agentic_cache_dir: Path = Field(default=Path("./data/agentic_cache"))

    # --- FRED ---
    fred_api_key: str = Field(default="")
    fred_cache_ttl_seconds: int = Field(default=3600)

    # --- SEC EDGAR ---
    sec_edgar_identity: str = Field(default="")
    sec_filing_cache_dir: Path = Field(default=Path("./data/sec_cache"))

    # --- Iceberg data catalog ---
    iceberg_rest_uri: str = Field(default="")
    iceberg_catalog_name: str = Field(default="aqp")
    iceberg_warehouse: Path = Field(default=Path("./data/iceberg"))
    iceberg_staging_dir: Path = Field(default=Path("./data/iceberg-staging"))
    iceberg_namespace_default: str = Field(default="aqp")
    iceberg_s3_warehouse: str = Field(default="")
    iceberg_max_rows_per_dataset: int = Field(default=5_000_000)
    iceberg_max_files_per_dataset: int = Field(default=2000)
    iceberg_health_check_timeout_seconds: float = Field(default=5.0)

    # --- S3 / MinIO ---
    s3_endpoint_url: str = Field(default="")
    s3_access_key: str = Field(default="")
    s3_secret_key: str = Field(default="")
    s3_region: str = Field(default="us-east-1")
    s3_path_style_access: bool = Field(default=True)

    # --- GDelt ---
    gdelt_manifest_url: str = Field(default="http://data.gdeltproject.org/gkg/index.html")
    gdelt_parquet_subdir: str = Field(default="gdelt")
    gdelt_subject_filter_only: bool = Field(default=True)
    gdelt_bigquery_project: str = Field(default="")
    gdelt_bigquery_table: str = Field(default="gdelt-bq.gdeltv2.gkg")

    # ------------------------------------------------------------------
    # Data engine + compute backends (Phase 1, data-fabric-expansion)
    # ------------------------------------------------------------------
    # Default executor flavor for new pipelines. ``auto`` lets
    # ``aqp.data.compute.selection.pick_backend`` promote based on the
    # ``compute_local_to_*`` thresholds.
    compute_backend_default: str = Field(default="auto")
    compute_local_to_dask_rows: int = Field(default=1_000_000)
    compute_local_to_ray_rows: int = Field(default=25_000_000)
    compute_local_to_dask_bytes: int = Field(default=256 * 1024 * 1024)
    compute_local_to_ray_bytes: int = Field(default=8 * 1024 * 1024 * 1024)

    # Dask / Ray cluster wiring. Empty means "spin up local cluster on
    # demand"; set to a scheduler URL for a remote cluster.
    dask_scheduler_address: str = Field(default="")
    dask_n_workers: int = Field(default=2)
    dask_threads_per_worker: int = Field(default=2)
    ray_init_kwargs_json: str = Field(default="")

    # Engine pipeline tuning.
    engine_default_chunk_rows: int = Field(default=50_000)
    engine_max_concurrent_pipelines: int = Field(default=2)
    engine_pipeline_timeout_seconds: int = Field(default=3600)

    # ------------------------------------------------------------------
    # Source library defaults (Phase 2, data-fabric-expansion)
    # ------------------------------------------------------------------
    fetcher_default_chunk_rows: int = Field(default=50_000)
    fetcher_max_concurrent: int = Field(default=4)
    fetcher_default_timeout_seconds: float = Field(default=120.0)
    fetcher_max_retries: int = Field(default=5)
    fetcher_user_agent: str = Field(
        default="aqp-fetcher/1.0 (+https://github.com/)"
    )
    finance_database_repo: str = Field(
        default="https://raw.githubusercontent.com/JerBouma/FinanceDatabase/main/financedatabase/compression"
    )
    polygon_api_key: str = Field(default="")
    tiingo_api_key: str = Field(default="")
    quandl_api_key: str = Field(default="")
    coingecko_api_key: str = Field(default="")
    akshare_enabled: bool = Field(default=False)

    # ------------------------------------------------------------------
    # Profile cache (Phase 3, data-fabric-expansion)
    # ------------------------------------------------------------------
    profile_cache_ttl_seconds: int = Field(default=3600)
    profile_cache_prefix: str = Field(default="aqp:profile")
    profile_topk: int = Field(default=10)
    profile_distinct_sample_rows: int = Field(default=200_000)
    profile_default_engine: str = Field(default="auto")  # auto | local | dask | ray

    # ------------------------------------------------------------------
    # Entity registry (Phase 4, data-fabric-expansion)
    # ------------------------------------------------------------------
    entity_extraction_enabled: bool = Field(default=True)
    entity_llm_enrichment_enabled: bool = Field(default=False)
    entity_llm_provider: str = Field(default="")
    entity_llm_model: str = Field(default="")
    entity_max_neighbors: int = Field(default=64)
    entity_dedup_similarity_threshold: float = Field(default=0.85)

    # ------------------------------------------------------------------
    # Dagster code location (Phase 5, data-fabric-expansion)
    # ------------------------------------------------------------------
    dagster_home: Path = Field(default=Path("./data/dagster_home"))
    dagster_grpc_host: str = Field(default="0.0.0.0")
    dagster_grpc_port: int = Field(default=4000)
    dagster_webserver_url: str = Field(default="")
    dagster_graphql_url: str = Field(default="")
    dagster_code_location: str = Field(default="aqp")
    dagster_module_path: str = Field(default="aqp.dagster.definitions")
    aqp_api_url_internal: str = Field(default="http://api.aqp.svc.cluster.local:8000")
    aqp_api_token: str = Field(default="")

    # ------------------------------------------------------------------
    # DataHub bidirectional sync (Phase 6, data-fabric-expansion)
    # ------------------------------------------------------------------
    datahub_sync_enabled: bool = Field(default=False)
    datahub_sync_direction: str = Field(default="push")  # push | pull | bidirectional
    datahub_sync_interval_seconds: int = Field(default=900)
    datahub_platform: str = Field(default="iceberg")
    datahub_platform_instance: str = Field(default="agentic-quant-platform")
    datahub_external_platforms: str = Field(default="")  # comma-separated

    # ------------------------------------------------------------------
    # Airbyte hybrid data fabric (full Airbyte + embedded PyAirbyte).
    # ------------------------------------------------------------------
    airbyte_enabled: bool = Field(default=False)
    airbyte_base_url: str = Field(default="http://airbyte-server.elt.svc.cluster.local:8001")
    airbyte_api_url: str = Field(default="")
    airbyte_workspace_id: str = Field(default="")
    airbyte_auth_token: str = Field(default="")
    airbyte_request_timeout_seconds: float = Field(default=30.0)
    airbyte_poll_interval_seconds: float = Field(default=5.0)
    airbyte_sync_timeout_seconds: int = Field(default=3600)
    airbyte_default_destination: str = Field(default="destination-s3-minio")
    airbyte_default_namespace: str = Field(default="aqp_airbyte")
    airbyte_embedded_cache_dir: Path = Field(default=Path("./data/airbyte/cache"))
    airbyte_staging_root: str = Field(default="s3://aqp-datasets/airbyte")
    airbyte_datahub_sync_enabled: bool = Field(default=True)

    # ------------------------------------------------------------------
    # dbt foundation (local DuckDB development project).
    # ------------------------------------------------------------------
    dbt_project_dir: Path = Field(default=Path("./data/dbt/aqp"))
    dbt_profiles_dir: Path = Field(default=Path("./data/dbt"))
    dbt_duckdb_path: Path = Field(default=Path("./data/dbt/aqp.duckdb"))
    dbt_target: str = Field(default="dev")
    dbt_generated_schema: str = Field(default="aqp_generated")
    dbt_generated_tag: str = Field(default="aqp_generated")
    dbt_artifact_retention: int = Field(default=25)
    dbt_command_timeout_seconds: int = Field(default=900)
    dbt_export_dir: Path = Field(default=Path("./data/dbt/exports"))

    @field_validator(
        "data_dir",
        "parquet_dir",
        "models_dir",
        "chroma_dir",
        "torchserve_model_store",
        "sec_filing_cache_dir",
        "agentic_cache_dir",
        "iceberg_warehouse",
        "iceberg_staging_dir",
        "agent_run_artifact_dir",
        "dagster_home",
        "airbyte_embedded_cache_dir",
        "dbt_project_dir",
        "dbt_profiles_dir",
        "dbt_duckdb_path",
        "dbt_export_dir",
    )
    @classmethod
    def _coerce_path(cls, v: Path | str) -> Path:
        return Path(v).expanduser().resolve()

    @property
    def datahub_external_platform_list(self) -> list[str]:
        """Parsed list of platform slugs we should pull from DataHub."""
        return [s.strip() for s in self.datahub_external_platforms.split(",") if s.strip()]

    @property
    def ray_init_kwargs(self) -> dict[str, object]:
        """Parsed Ray ``ray.init`` kwargs from JSON env."""
        import json

        raw = (self.ray_init_kwargs_json or "").strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except Exception:
            return {}
        return dict(value) if isinstance(value, dict) else {}

    @property
    def universe_list(self) -> list[str]:
        return [s.strip() for s in self.default_universe.split(",") if s.strip()]

    @property
    def webui_cors_origin_list(self) -> list[str]:
        """Parsed list of CORS origins for the Next.js webui."""
        return [s.strip() for s in self.webui_cors_origins.split(",") if s.strip()]

    @property
    def stream_universe_list(self) -> list[str]:
        raw = self.stream_universe.strip() or self.default_universe
        return [s.strip() for s in raw.split(",") if s.strip()]

    @property
    def local_data_roots_list(self) -> list[Path]:
        return [
            Path(p.strip()).expanduser().resolve()
            for p in self.local_data_roots.split(",")
            if p.strip()
        ]

    @property
    def otel_enabled(self) -> bool:
        return bool(self.otel_endpoint)

    def provider_for_tier(self, tier: str) -> str:
        requested = str(tier or "deep").strip().lower()
        if requested == "quick" and self.llm_provider_quick.strip():
            return self.llm_provider_quick.strip().lower()
        if requested == "deep" and self.llm_provider_deep.strip():
            return self.llm_provider_deep.strip().lower()
        return self.llm_provider.strip().lower() or "ollama"

    def api_key_for_provider(self, provider_slug: str) -> str:
        slug = str(provider_slug or "").strip().lower()
        mapping: dict[str, tuple[str, str]] = {
            "openai": ("openai_api_key", "OPENAI_API_KEY"),
            "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
            "google": ("google_api_key", "GOOGLE_API_KEY"),
            "xai": ("xai_api_key", "XAI_API_KEY"),
            "deepseek": ("deepseek_api_key", "DEEPSEEK_API_KEY"),
            "groq": ("groq_api_key", "GROQ_API_KEY"),
            "openrouter": ("openrouter_api_key", "OPENROUTER_API_KEY"),
            "ollama": ("", ""),
        }
        attr_name, env_name = mapping.get(slug, ("", ""))
        if attr_name:
            value = str(getattr(self, attr_name, "") or "").strip()
            if value:
                return value
        if env_name:
            return str(os.environ.get(env_name, "") or "").strip()
        return ""

    def finops_labels(self, **extra: str) -> dict[str, str]:
        """Return the canonical FinOps tag map for any cloud-bound resource.

        Every Celery dispatch (via the ``before_task_publish`` signal in
        :mod:`aqp.tasks.celery_app`), Kubernetes pod (via Helm /
        Kustomize ``commonLabels``), and MLflow run (via
        :mod:`aqp.mlops.mlflow_client`) calls this helper so the same
        five keys appear everywhere — making the cost-attribution chain
        from Grafana panel → cAdvisor pod label → Settings field
        unbroken.

        Pass ``strategy_id`` / ``agent_run_id`` / ``backtest_id`` etc. as
        ``**extra`` to enrich the base tags for the specific dispatch.
        """
        labels: dict[str, str] = {
            "project": str(self.project_tag or "aqp-default"),
            "cost_center": str(self.cost_center or "quant-research-01"),
            "owner": str(self.owner or "system-orchestrator"),
            "data_classification": str(self.data_classification or "proprietary-alpha"),
            "environment": str(self.env or "dev"),
        }
        for k, v in extra.items():
            if v is None:
                continue
            sval = str(v).strip()
            if not sval:
                continue
            labels[k] = sval
        return labels


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
