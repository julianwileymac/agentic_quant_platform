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
    # --- Data-pipeline Director (Nemotron by default). The Director is
    # invoked by ``aqp.data.pipelines.director.plan_ingestion`` to
    # review the discovery brief and decide on namespaces, table names,
    # row floors, and per-member skip lists before materialisation.
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
    # vLLM — OpenAI-compatible HTTP API. Either a containerised service
    # (the docker-compose ``vllm`` profile) or any external endpoint a
    # user runs themselves. The ``vllm`` provider in the LLM router
    # dispatches through LiteLLM's ``openai/`` adapter using these.
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

    # --- MLflow ---
    mlflow_tracking_uri: str = Field(default="http://localhost:5000")
    mlflow_experiment: str = Field(default="aqp-default")
    mlflow_registry_uri: str = Field(default="")  # "" = same as tracking URI
    mlflow_serve_host: str = Field(default="0.0.0.0")
    mlflow_serve_port: int = Field(default=5001)

    # --- Ray Serve ---
    # When targeting the rpi_kubernetes cluster use
    # ``ray://ray-head.mlops.svc.cluster.local:10001`` for the client API and
    # ``http://ray-serve.mlops.svc.cluster.local:8000`` for the HTTP ingress.
    ray_address: str = Field(default="auto")  # ``auto`` = start local head
    ray_serve_http_host: str = Field(default="0.0.0.0")
    ray_serve_http_port: int = Field(default=8000)
    ray_serve_route_prefix: str = Field(default="/aqp")

    # --- TorchServe ---
    torchserve_inference_url: str = Field(default="http://localhost:8080")
    torchserve_management_url: str = Field(default="http://localhost:8081")
    torchserve_model_store: Path = Field(default=Path("./data/torchserve/model-store"))

    # --- Sentiment / FinGPT ---
    # Default HuggingFace model id for SentimentScorer. ``yiyanghkust/finbert-tone``
    # is free and open; gated FinGPT LoRA checkpoints can be swapped in here.
    sentiment_model: str = Field(default="yiyanghkust/finbert-tone")
    fingpt_forecaster_model: str = Field(default="")  # "" = route via LLM router
    finrobot_default_tier: str = Field(default="deep")

    # --- Cross-repo integration (agentic_assistants + rpi_kubernetes) ---
    # The agentic_assistants lineage API is consumed via its REST surface
    # and keeps a shared dataset→run→model graph across both repos.
    agentic_assistants_api: str = Field(default="")
    # MinIO / S3 bucket for shared artifacts (maps to the MinIO service
    # deployed by rpi_kubernetes/base-services/minio).
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
    # Comma-separated list of allowed origins for CORS. The Next dev server
    # uses :3000 by default; production deployments should narrow this to
    # the canonical hostname. The legacy ``*`` behaviour is retained when
    # this is left empty so existing clients (Solara on :8765) keep working.
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

    # Optional comma-separated list of extra Parquet roots merged into the
    # DuckDB ``bars`` view. Useful when users drop their own Parquet files
    # outside the default lake (e.g. vendor exports on a mounted drive).
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
    alpaca_base_url: str = Field(default="")  # "" = use SDK default

    # --- Interactive Brokers (TWS / IB Gateway) ---
    ibkr_host: str = Field(default="127.0.0.1")
    ibkr_port: int = Field(default=7497)  # 7497 = paper, 7496 = live
    ibkr_client_id: int = Field(default=1)

    # --- Tradier (generic REST example) ---
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

    # --- OpenTelemetry ---
    otel_endpoint: str = Field(default="")  # "" disables tracing
    otel_service_name: str = Field(default="aqp")
    otel_sample_ratio: float = Field(default=1.0)
    otel_protocol: str = Field(default="grpc")  # grpc | http/protobuf

    # --- Kafka (streaming pipeline) ---
    # The ingesters produce to Kafka and the KafkaDataFeed consumes from it.
    # On the rpi_kubernetes cluster the bootstrap server is
    # ``trading-kafka-kafka-bootstrap.data-services.svc.cluster.local:9092``.
    kafka_bootstrap: str = Field(default="localhost:9092")
    kafka_client_id: str = Field(default="aqp")
    kafka_compression: str = Field(default="zstd")  # zstd | lz4 | snappy | none
    kafka_acks: str = Field(default="all")  # all | 1 | 0
    kafka_security_protocol: str = Field(default="PLAINTEXT")  # PLAINTEXT | SSL | SASL_SSL | SASL_PLAINTEXT
    kafka_sasl_mechanism: str = Field(default="")  # PLAIN | SCRAM-SHA-256 | SCRAM-SHA-512
    kafka_sasl_username: str = Field(default="")
    kafka_sasl_password: str = Field(default="")
    kafka_topic_prefix: str = Field(default="")  # Prefix prepended to every topic; empty for plain names
    kafka_consumer_group: str = Field(default="aqp-live")

    # --- Streaming ingester configuration ---
    stream_universe: str = Field(default="")  # Comma-separated tickers; "" = fall back to default_universe
    stream_config_file: str = Field(default="")  # YAML with option/future contracts
    # IBKR ``reqMarketDataType`` codes: 1 live, 2 frozen, 3 delayed, 4 delayed-frozen.
    stream_market_data_type: int = Field(default=3)
    stream_scanner_interval_sec: int = Field(default=300)
    stream_scanner_enabled: bool = Field(default=False)
    stream_include_quotes: bool = Field(default=True)
    stream_include_trades: bool = Field(default=True)
    stream_include_bars: bool = Field(default=True)
    stream_metrics_port: int = Field(default=9300)
    stream_health_port: int = Field(default=9301)

    # --- Alpaca streaming feed selection ---
    # ``iex`` free tier, ``sip`` paid tier, ``delayed_sip`` 15-min delayed.
    alpaca_feed: str = Field(default="iex")
    news_provider: str = Field(default="yfinance")
    agentic_default_preset: str = Field(default="trader_crew_quick")
    agentic_cache_dir: Path = Field(default=Path("./data/agentic_cache"))

    # --- FRED (St. Louis Fed economic data) ---
    fred_api_key: str = Field(default="")
    fred_cache_ttl_seconds: int = Field(default=3600)

    # --- SEC EDGAR (via edgartools) ---
    # edgartools requires an identity string ``"Name email@example.com"``
    # to comply with SEC's fair-use guidance. When empty, the adapter
    # will refuse to issue requests.
    sec_edgar_identity: str = Field(default="")
    sec_filing_cache_dir: Path = Field(default=Path("./data/sec_cache"))

    # --- Iceberg data catalog ---
    # The Iceberg-first generic catalog. When ``iceberg_rest_uri`` is set we
    # use the Tabular/Lakekeeper-style REST catalog; otherwise we fall back
    # to a local PyIceberg ``sql`` catalog (sqlite metadata, filesystem
    # warehouse) so unit tests and ``make api`` work without Docker.
    iceberg_rest_uri: str = Field(default="")
    iceberg_catalog_name: str = Field(default="aqp")
    # Filesystem path used when the SQL fallback catalog is active. When the
    # REST catalog is configured this path is also where the SQLite metadata
    # store lives (warehouse data goes to S3/MinIO instead).
    #
    # In Docker Compose this is overridden via ``AQP_ICEBERG_WAREHOUSE`` to
    # point at ``/warehouse/iceberg``, which is the host bind mount of
    # ``D:/aqp-warehouse``. The ``./data/iceberg`` Python default keeps
    # native (non-container) workflows working without extra setup.
    iceberg_warehouse: Path = Field(default=Path("./data/iceberg"))
    # Scratch directory for unzipping / staging large archives during
    # ingestion. Lives next to the warehouse so it benefits from the same
    # host bind mount and isn't lost when the container restarts.
    iceberg_staging_dir: Path = Field(default=Path("./data/iceberg-staging"))
    iceberg_namespace_default: str = Field(default="aqp")
    # When using the REST catalog with MinIO, surface the warehouse URI
    # explicitly. ``s3a://aqp-iceberg`` is the typical bucket layout.
    iceberg_s3_warehouse: str = Field(default="")
    # Default cap on how many rows we materialize per logical dataset before
    # flagging the table as "truncated" in lineage. 5M handles most regulatory
    # CSVs; the harness can override to slice through 30 GB ZIPs in chunks.
    iceberg_max_rows_per_dataset: int = Field(default=5_000_000)
    # Cap on how many files we will pull from a single ZIP / folder when
    # materializing one logical dataset. Protects against runaway extraction.
    iceberg_max_files_per_dataset: int = Field(default=2000)

    # --- S3 / MinIO credentials shared by Iceberg + general object storage ---
    s3_endpoint_url: str = Field(default="")
    s3_access_key: str = Field(default="")
    s3_secret_key: str = Field(default="")
    s3_region: str = Field(default="us-east-1")
    s3_path_style_access: bool = Field(default=True)

    # --- GDelt (Global Knowledge Graph 2.0) ---
    gdelt_manifest_url: str = Field(default="http://data.gdeltproject.org/gkg/index.html")
    gdelt_parquet_subdir: str = Field(default="gdelt")  # under ``parquet_dir``
    # Drop rows that don't mention a registered :class:`Instrument`. When
    # false, all manifest rows are kept (scales to ~2.5 TB/year).
    gdelt_subject_filter_only: bool = Field(default=True)
    gdelt_bigquery_project: str = Field(default="")
    gdelt_bigquery_table: str = Field(default="gdelt-bq.gdeltv2.gkg")

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
    )
    @classmethod
    def _coerce_path(cls, v: Path | str) -> Path:
        return Path(v).expanduser().resolve()

    @property
    def universe_list(self) -> list[str]:
        return [s.strip() for s in self.default_universe.split(",") if s.strip()]

    @property
    def webui_cors_origin_list(self) -> list[str]:
        """Parsed list of CORS origins for the Next.js webui.

        Empty list means "allow all" (the legacy ``*`` behaviour). Used by
        :mod:`aqp.api.main` to seed the FastAPI CORSMiddleware.
        """
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
