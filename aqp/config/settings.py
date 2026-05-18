"""Global :class:`Settings` — process-wide, env-backed, lru-cached.

This is the same Pydantic model that lived at ``aqp/config.py`` before the
tenancy refactor, with a small set of new ``AQP_DEFAULT_*_ID`` /
``AQP_AUTH_PROVIDER`` knobs for the multi-tenant seed.

Reading ``settings`` returns the *baseline* config — the bottom of the
six-layer overlay stack (global > org > team > user > workspace > project).
For any code path that has a :class:`aqp.auth.context.RequestContext`, prefer
:func:`aqp.config.resolve_config` so per-tenant overrides apply.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from aqp.config.defaults import (
    DEFAULT_LAB_ID,
    DEFAULT_ORG_ID,
    DEFAULT_PROJECT_ID,
    DEFAULT_TEAM_ID,
    DEFAULT_USER_ID,
    DEFAULT_WORKSPACE_ID,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AQP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- FinOps / Cloud Governance ---
    project_tag: str = Field(default="aqp-default")
    cost_center: str = Field(default="quant-research-01")
    owner: str = Field(default="system-orchestrator")
    data_classification: str = Field(default="proprietary-alpha")

    # --- Tenancy defaults (default-org / -team / -user / -workspace / -project / -lab) ---
    # Override these only if you've migrated a cluster off the canonical seed
    # and need to point legacy resources at a different tenancy bucket.
    default_org_id: str = Field(default=DEFAULT_ORG_ID)
    default_team_id: str = Field(default=DEFAULT_TEAM_ID)
    default_user_id: str = Field(default=DEFAULT_USER_ID)
    default_workspace_id: str = Field(default=DEFAULT_WORKSPACE_ID)
    default_project_id: str = Field(default=DEFAULT_PROJECT_ID)
    default_lab_id: str = Field(default=DEFAULT_LAB_ID)
    auth_provider: str = Field(default="local")  # local | auth0 | oidc | mock | jwt | msal_entra
    # ``auth_required`` is the cluster-default guard: when true and
    # ``auth_provider`` is not ``local``, API dependencies refuse
    # missing Bearer/session tokens instead of silently falling back to
    # the deterministic default user. Local developer mode remains
    # available only when AQP_AUTH_PROVIDER=local.
    auth_required: bool = Field(default=True)
    auth_oidc_issuer: str = Field(default="")
    auth_oidc_client_id: str = Field(default="")
    auth_oidc_client_secret: str = Field(default="")
    auth_oidc_audience: str = Field(default="")
    auth_oidc_jwks_ttl_seconds: int = Field(default=3600)
    auth_oidc_leeway_seconds: int = Field(default=60)
    # --- MSAL / Microsoft Entra ID (multi-tenant identity provider) ---
    # Set ``auth_provider=msal_entra`` to make MsalEntraProvider the active
    # IdentityProvider. The multi-tenant default authority
    # ``/organizations`` accepts users from any Entra tenant (B2B / external
    # enterprise clients); pin to ``/{tenant_id}`` for single-tenant.
    # See docs/msal-entra-setup.md for the full app-reg walkthrough.
    auth_msal_tenant_id: str = Field(default="")
    auth_msal_client_id: str = Field(default="")
    auth_msal_client_secret: str = Field(default="")
    auth_msal_authority: str = Field(
        default="https://login.microsoftonline.com/organizations"
    )
    auth_msal_redirect_uri: str = Field(default="")
    auth_msal_scopes: str = Field(
        default="openid profile email offline_access User.Read"
    )
    auth_msal_multi_tenant: bool = Field(default=True)
    # Allow external (B2B / non-home) tenants to provision new
    # EntraTenantLink rows on first login. The link starts in
    # ``pending`` state; an AQP super-admin promotes to ``active``.
    auth_msal_b2b_enabled: bool = Field(default=True)
    auth_msal_known_tenants: str = Field(default="")  # CSV of tenant_ids
    # --- Auth0 Management API (account management, MFA, sessions) ---
    # The Management API M2M Application in the Auth0 tenant is the
    # ingress for /me/* mutations that have no user-facing auth code
    # equivalent (MFA enrollment, session revocation, password tickets,
    # user delete, connected-account link/unlink). The audience always
    # has the shape ``https://<tenant>/api/v2/``. The client secret is
    # resolved via :class:`aqp.credentials.CredentialResolver` per rule
    # 26 — never read ``auth0_mgmt_api_client_secret`` directly from
    # service code.
    auth0_mgmt_api_audience: str = Field(default="")
    auth0_mgmt_api_client_id: str = Field(default="")
    auth0_mgmt_api_client_secret: str = Field(default="")
    # Auth0 connection names. The defaults match a fresh Auth0 tenant
    # (Username-Password-Authentication for email/password, social
    # connections for Google, an Enterprise Connection named
    # ``azure-ad-myorg`` for Microsoft Entra ID). Operators rename via
    # the dashboard and override these env vars.
    auth0_database_connection: str = Field(default="Username-Password-Authentication")
    auth0_microsoft_connection: str = Field(default="azure-ad-myorg")
    auth0_google_connection: str = Field(default="google-oauth2")
    # Reject logins where Auth0 reports the email as unverified. Keeps
    # the audit trail clean and prevents account-takeover via unverified
    # secondary emails on social providers.
    auth_require_email_verified: bool = Field(default=True)
    # --- Tenancy invites (Phase 1.7) ---
    auth_invite_ttl_hours: int = Field(default=72)
    auth_invite_secret: str = Field(default="")  # HMAC secret for token hashing; >=32 bytes
    # --- Security audit log (Phase 1.8) ---
    # When false, `aqp.auth.audit.emit_audit_event` is a no-op. Keep
    # enabled in production; tests opt out via the audit_disabled
    # fixture so they don't need the Postgres table.
    auth_audit_enabled: bool = Field(default=True)
    auth_audit_retention_days: int = Field(default=365)
    # --- Federated identity (M3) ---
    # ``auth_login_callback`` / ``auth_logout_callback`` are the
    # backend-rendered redirect URIs for the SPA login flow. Empty in
    # local-mode deployments; set when ``auth_provider`` is auth0 / oidc.
    auth_login_callback: str = Field(default="")
    auth_logout_callback: str = Field(default="")
    # ``auth_session_secret`` keys the JWE-encrypted cookie store; must be
    # at least 32 bytes in production. Generate with ``openssl rand -hex 32``.
    auth_session_secret: str = Field(default="")
    # ``cookie`` (default) keeps state in the encrypted cookie itself;
    # ``redis`` keeps state in Redis with the cookie holding only the
    # session id. Pick ``redis`` when the session payload exceeds 4KB.
    auth_session_backend: str = Field(default="cookie")  # cookie | redis
    # M2M token issuer toggle. When true, services like Polaris / Trino /
    # MinIO reach for short-lived tokens minted via the active
    # IdentityProvider's client_credentials flow instead of static
    # bootstrap credentials.
    auth_m2m_enabled: bool = Field(default=False)
    auth_m2m_audience: str = Field(default="")
    auth_m2m_scope: str = Field(default="")
    auth_m2m_token_ttl_seconds: int = Field(default=900)
    # --- SCIM 2.0 provisioning (Auth0 -> AQP tenancy) ---
    # AQP exposes /scim/v2/* so Auth0 Actions / jobs can upsert users
    # and groups into the AQP tenancy tables. The endpoint is disabled
    # by default until the cluster deployment provides either an M2M
    # audience or a static bearer-token hash.
    auth_scim_enabled: bool = Field(default=False)
    auth_scim_m2m_audience: str = Field(default="")
    auth_scim_bearer_token_hash: str = Field(default="")
    auth_scim_default_org_slug: str = Field(default="wiley-tech")
    # --- Kubernetes adapter (M4) ---
    # ``none`` (default) keeps AQP standalone. ``rpi_cluster`` activates
    # automatically when ``cluster_mgmt_url`` is set. ``in_cluster`` uses
    # the Kubernetes Python SDK with the active kubeconfig / pod SA.
    # ``local_compose`` shells out to ``docker compose`` and powers the
    # platform overlay. Cloud adapters (``aws_eks`` / ``gcp_gke`` /
    # ``azure_aks``) auto-promote when ``default_cloud_provider`` is set.
    kubernetes_adapter: str = Field(default="")  # none | rpi_cluster | in_cluster | local_compose | aws_eks | gcp_gke | azure_aks
    # Canonical deployment topology manifest consumed by Terraform entrypoints,
    # control-plane routes, and the frontend deployment views.
    deployment_topology_path: str = Field(
        default="./configs/deployment/topology.yaml"
    )
    # --- Default cloud provider (multi-cloud + tenant onboarding) ---
    # Empty means "local" — every Terraform / KubernetesAdapter /
    # CredentialResolver default short-circuits to local execution.
    # Set to one of ``aws|gcp|azure`` to make the matching cloud
    # adapter + secret store + Terraform module the active default.
    default_cloud_provider: str = Field(default="")
    default_organization_name: str = Field(default="Wiley Tech")
    default_organization_slug: str = Field(default="wiley-tech")
    default_admin_email: str = Field(default="julian@wiley.tech")
    default_admin_display_name: str = Field(default="Julian")
    auth_session_cookie: str = Field(default="aqp_session")
    auth_workspace_header: str = Field(default="X-AQP-Workspace")
    auth_project_header: str = Field(default="X-AQP-Project")
    auth_lab_header: str = Field(default="X-AQP-Lab")
    auth_user_header: str = Field(default="X-AQP-User")
    auth_org_header: str = Field(default="X-AQP-Org")
    auth_team_header: str = Field(default="X-AQP-Team")
    # --- Semantic LLM completion cache (Phase 5 multi-tenant rollout) ---
    # Vectorises the last user-turn of every router_complete call and
    # cosine-searches an aqp:llm:semantic:* Redis index. Hit returns the
    # cached completion; miss falls through to the foundational model.
    # Disabled by default so the base Ollama-only install keeps working
    # without redis / embeddings configured.
    llm_semantic_cache_enabled: bool = Field(default=False)
    llm_semantic_cache_threshold: float = Field(default=0.95)
    llm_semantic_cache_ttl_seconds: int = Field(default=3600)
    llm_semantic_cache_max_entries: int = Field(default=10000)
    # Phase 4 — auth enforcement sweep. ``strict`` returns 401/403 on
    # violations (production). ``permissive`` logs them + tags the
    # OTEL span without blocking the request so the rollout can flip
    # to ``strict`` only when the dashboard shows zero would-be denies.
    auth_enforce: str = Field(default="strict")  # strict | permissive
    # AQP-namespaced custom claim prefix injected by the Auth0 Action.
    # See ``docs/auth0-actions.md``. Decoupled from the issuer URL so
    # the same Action works against staging / prod tenants without
    # rebuilding the SPA.
    auth_claims_namespace: str = Field(default="https://aqp/")

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
    vllm_base_url: str = Field(default="")
    vllm_api_key: str = Field(default="")
    vllm_default_model: str = Field(default="nemotron")

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_pubsub_url: str = Field(default="redis://localhost:6379/1")

    # --- Metadata cache (data fabric phase 0) ---
    # Whitelist-only entity dropdowns (datasets / namespaces / sinks /
    # connectors / projects / credentials) read from a Redis prefetch
    # layer. Falls back to in-memory when Redis is unreachable so unit
    # tests + the local dev loop never hard-fail.
    cache_enabled: bool = Field(default=True)
    cache_redis_url: str = Field(default="")  # empty -> reuse redis_url
    cache_redis_db: int = Field(default=2)
    cache_key_prefix: str = Field(default="aqp:cache")
    # Periodic full re-prefetch interval (seconds). Write-through keeps
    # the cache live; this is a safety-net rebuild for clock drift.
    cache_refresh_interval_s: int = Field(default=300)
    # Master data (kinds, namespaces) lives ~24h; instance data
    # (datasets, connectors) lives 15m. The prefetcher resets both on
    # every full run.
    cache_master_ttl_s: int = Field(default=86400)
    cache_instance_ttl_s: int = Field(default=900)
    cache_fulltext_index: bool = Field(default=True)
    # TTL jitter (0-50%) applied on every cache.expire() call to prevent
    # the thundering-herd / cache-stampede pattern where dozens of keys
    # expire on the same second and trigger a wave of Postgres rebuilds.
    cache_ttl_jitter_pct: int = Field(default=10)
    # L1 in-memory layer (cachetools.TTLCache) in front of the L2 Redis
    # store. Sub-100ns dropdown reads at the cost of accepting a few
    # seconds of staleness across worker processes.
    cache_l1_enabled: bool = Field(default=True)
    cache_l1_ttl_s: int = Field(default=5)
    cache_l1_max_entries: int = Field(default=2048)
    # Single-flight coalescing for cold cache reads — concurrent misses
    # on the same (category, query) only fire a single Postgres query
    # while siblings await its result.
    cache_single_flight_enabled: bool = Field(default=True)

    # --- Airbyte builder (data fabric phase 2) ---
    # The graphical builder emits AQP-native Fetcher stubs into
    # ``aqp/data/fetchers/userland/<slug>.py``. The two switches below
    # gate the write path so production deploys can keep codegen
    # disabled even when the API is reachable.
    airbyte_builder_codegen_enabled: bool = Field(default=True)
    airbyte_builder_overwrite: bool = Field(default=False)

    # --- Postgres ---
    postgres_dsn: str = Field(
        default="postgresql+psycopg2://aqp:aqp@localhost:5432/aqp",
    )
    postgres_async_dsn: str = Field(
        default="postgresql+asyncpg://aqp:aqp@localhost:5432/aqp",
    )
    postgres_pool_size: int = Field(default=10)
    postgres_max_overflow: int = Field(default=20)
    postgres_pool_timeout_seconds: int = Field(default=30)
    postgres_pool_recycle_seconds: int = Field(default=1800)

    # --- Entity graph store ---
    graph_store: str = Field(default="postgres")  # postgres | neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="aqpneo4j")
    neo4j_database: str = Field(default="neo4j")
    entity_graph_sync_enabled: bool = Field(default=True)

    # --- Ownership graph (Phase 2 of the multi-tenant graph expansion) ---
    # Postgres remains the canonical store. ``neo4j`` flips reads onto a
    # mirror projected from the SQLAlchemy after_flush events drained by
    # :mod:`aqp.tasks.ownership_tasks`. ``postgres`` keeps everything in
    # Postgres (uses ``WITH RECURSIVE`` queries on the canonical tables).
    ownership_graph_store: str = Field(default="postgres")  # postgres | neo4j
    # ``sync`` blocks the FastAPI request on the Neo4j write (only useful
    # for tests). ``async`` (default) queues events for the drain task.
    # ``mirror`` writes to both stores from the drain task so reads can
    # cross-check during rollout.
    ownership_sync_mode: str = Field(default="async")  # sync | async | mirror
    ownership_sync_batch_size: int = Field(default=500)
    # The full Postgres -> Neo4j resync runs on this cadence to heal
    # any events lost between an outage and recovery. Cheap to run.
    ownership_resync_interval_s: int = Field(default=1800)
    active_instrument_cache_ttl_seconds: int = Field(default=300)
    service_control_enabled: bool = Field(default=False)
    service_log_tail_lines: int = Field(default=200)
    polaris_base_url: str = Field(default="http://localhost:8183")
    polaris_realm: str = Field(default="POLARIS")
    polaris_client_id: str = Field(default="root")
    polaris_client_secret: str = Field(default="s3cr3t")
    iceberg_auto_bootstrap: bool = Field(default=False)
    iceberg_catalog_warehouse_name: str = Field(default="quickstart_catalog")
    iceberg_catalog_storage_type: str = Field(default="FILE")  # FILE | S3
    iceberg_default_base_location: str = Field(default="file:///warehouse/iceberg/quickstart_catalog")
    iceberg_principal_name: str = Field(default="aqp_runtime")
    iceberg_principal_role: str = Field(default="aqp_runtime_role")
    iceberg_catalog_role: str = Field(default="aqp_runtime_catalog_role")
    iceberg_catalog_privilege: str = Field(default="CATALOG_MANAGE_CONTENT")
    bootstrap_state_dir: Path = Field(default=Path("./data/bootstrap"))
    trino_admin_user: str = Field(default="aqp")
    trino_admin_source: str = Field(default="aqp-service-manager")

    # --- ChromaDB ---
    chroma_host: str = Field(default="localhost")
    chroma_port: int = Field(default=8001)
    chroma_embedding_model: str = Field(default="all-MiniLM-L6-v2")

    # --- Hierarchical RAG (Redis Stack / RediSearch) ---
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
    # Math-aware research-paper RAG (2026 research-report consolidation).
    rag_pdf_parser: str = Field(
        default="marker",
        description=(
            "Preferred PDF parser for the research_papers corpus. Selector "
            "chain falls back to nougat / mathpix / pypdf when unavailable."
        ),
    )
    rag_paper_root: Path = Field(
        default=Path("./data/research_papers"),
        description="Filesystem root where uploaded research PDFs are stored.",
    )
    rag_paper_max_mb: int = Field(
        default=50,
        description="Maximum single-PDF upload size in megabytes.",
    )
    # MathPix credentials are typically resolved via CredentialResolver,
    # but Settings exposes the keys so docker / k8s envs can set them.
    mathpix_app_id: str = Field(default="")
    mathpix_app_key: str = Field(default="")

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
    mlflow_registry_uri: str = Field(default="")
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

    # --- ML engine major expansion (Alembic 0025) ---
    ml_prediction_audit_enabled: bool = Field(default=False)
    ml_prediction_audit_max_rows: int = Field(default=1000)
    tf_native_enabled: bool = Field(default=False)
    hf_timeseries_enabled: bool = Field(default=False)
    hf_finbert_model: str = Field(default="ProsusAI/finbert")
    hf_timeseries_model: str = Field(default="huggingface/time-series-transformer-tourism-monthly")
    ml_workbench_max_csv_mb: int = Field(default=20)

    # --- RL layer (FinRL + FinRobot inspired refactor, Alembic 0026) ---
    # Iceberg targets for trajectory / equity-curve / action-log / reward-decomp persistence.
    # All four go through ``aqp.data.iceberg_catalog.append_arrow`` via
    # :class:`aqp.rl.trajectories.iceberg_writer.IcebergTrajectoryStore`.
    rl_trajectory_namespace: str = Field(default="rl")
    rl_trajectory_table: str = Field(default="trajectories")
    rl_equity_table: str = Field(default="equity_curves")
    rl_action_log_table: str = Field(default="action_logs")
    rl_reward_decomp_table: str = Field(default="reward_decomposition")
    rl_persist_trajectories: bool = Field(default=True)
    rl_trajectory_flush_rows: int = Field(default=1000)
    # Default RL backend used by the RLRuntime when ``spec.agent`` doesn't
    # specify a framework. One of: ``sb3``, ``elegantrl``, ``rllib``, ``cleanrl``.
    rl_default_framework: str = Field(default="sb3")
    # When true the runtime will refuse to run if Iceberg is unreachable
    # (use during full data-plane testing). Default is false so local-only
    # work falls back to the in-memory trajectory store.
    rl_require_iceberg: bool = Field(default=False)

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

    # --- Visualization layer (Superset + Trino + Bokeh) ---
    superset_base_url: str = Field(default="http://localhost:8088")
    superset_public_url: str = Field(default="http://localhost:8088")
    superset_username: str = Field(default="admin")
    superset_password: str = Field(default="admin")
    superset_provider: str = Field(default="db")
    superset_guest_username: str = Field(default="aqp_guest")
    superset_guest_first_name: str = Field(default="AQP")
    superset_guest_last_name: str = Field(default="Guest")
    superset_default_dashboard_uuid: str = Field(default="")
    trino_uri: str = Field(default="trino://trino@localhost:8080/iceberg")
    trino_catalog: str = Field(default="iceberg")
    trino_schema: str = Field(default="aqp")
    # Optional override for REST probes when the JDBC host differs from the HTTP UI port.
    trino_http_url: str = Field(default="")
    visualization_cache_dir: Path = Field(default=Path("./data/visualizations/cache"))
    visualization_cache_ttl_seconds: int = Field(default=3600)
    visualization_default_limit: int = Field(default=1000)
    # Two-tier cache backend used by the Bokeh renderer:
    # - "both" (default): consult Redis first, fall back to file; write to both.
    # - "redis": Redis only (loses cache across restarts when Redis is wiped).
    # - "file": file only (no shared cache across worker replicas).
    visualization_cache_backend: str = Field(default="both")
    visualization_bundle_dir: Path = Field(default=Path("./data/visualizations/bundles"))
    datahub_superset_sync_enabled: bool = Field(default=False)

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
    # Host->container mapping used by local ingest APIs/tasks.
    # Format: "C:/host/root=>/container/root,/another/host=>/another/container"
    local_ingest_path_map: str = Field(default="")
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

    # --- Interactive Brokers ---
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
    alpha_vantage_rps_limit: int = Field(default=8)
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
    # Env var names AQP_DATAHUB_ASPECT_PUSH_ENABLED / AQP_DATAHUB_ASPECT_PULL_ENABLED
    # (env_prefix="AQP_" is applied automatically by pydantic-settings to the
    # lowercase field names).
    datahub_aspect_push_enabled: bool = Field(
        default=False,
        description=(
            "Soft-rollout flag for emitting EntityAspect writes to DataHub via MCP."
        ),
    )
    datahub_aspect_pull_enabled: bool = Field(
        default=False,
        description=(
            "Soft-rollout flag for polling external DataHub aspects into entity_aspects."
        ),
    )

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

    # --- Kafka admin (Data layer expansion) ---
    # Optional overrides for the native admin client (defaults inherit
    # from the regular kafka_* settings). Lets the AdminClient point at
    # a separate listener (PLAIN bootstrap for ops, SCRAM for runtime).
    kafka_admin_bootstrap: str = Field(default="")
    kafka_admin_security_protocol: str = Field(default="")
    kafka_admin_sasl_mechanism: str = Field(default="")
    kafka_admin_sasl_username: str = Field(default="")
    kafka_admin_sasl_password: str = Field(default="")
    kafka_admin_schema_registry_url: str = Field(default="")
    schema_registry_url: str = Field(default="")  # generic alias

    # --- Flink (Data layer expansion) ---
    flink_rest_url: str = Field(default="")
    flink_namespace: str = Field(default="data-services")
    flink_session_cluster_name: str = Field(default="flink-session")
    flink_savepoint_dir: str = Field(default="s3://flink-savepoints")
    flink_factor_jar_uri: str = Field(default="s3://flink-jobs/factor_compute.jar")
    flink_factor_entry_class: str = Field(default="io.aqp.flink.factor.FactorJob")

    # --- Cluster management proxy (rpi_kubernetes) ---
    cluster_mgmt_url: str = Field(default="")
    cluster_mgmt_token: str = Field(default="")

    # --- Terraform IaC control plane ----------------------------------------
    # Centralized Terraform IaC for multi-cloud + local + baremetal. Five
    # state backends (``local | s3 | azurerm | gcs | hcp``) are routed by
    # :class:`aqp.terraform.runtime.TerraformRuntime`. CDKTF was
    # deprecated 2025-12-10 by HashiCorp, so Python-side codegen uses the
    # Jinja2 emitters under :mod:`aqp.terraform.codegen` (matches the
    # existing pattern in :mod:`aqp.streaming.templates`).
    terraform_binary: str = Field(default="terraform")
    terraform_workspaces_dir: Path = Field(default=Path("./data/terraform/workspaces"))
    terraform_state_backend: str = Field(default="local")  # local | s3 | azurerm | gcs | hcp
    terraform_plugin_cache_dir: Path = Field(default=Path("./data/terraform/plugin-cache"))
    # Optional Terraform CLI config file path. When set and the file exists
    # the runner exports ``TF_CLI_CONFIG_FILE`` so provider mirrors /
    # installation rules can be enforced centrally.
    terraform_cli_config_file: str = Field(default="")
    # Bounded retry policy for ``terraform init`` on transient provider
    # fetch/network errors (connection reset, TLS timeout, etc).
    terraform_init_retry_attempts: int = Field(default=3)
    terraform_init_retry_backoff_seconds: float = Field(default=2.0)
    terraform_init_retry_max_backoff_seconds: float = Field(default=30.0)
    terraform_parallelism: int = Field(default=10)
    terraform_runner_image: str = Field(default="aqp-terraform-runner:latest")
    terraform_runner_namespace: str = Field(default="aqp-system")
    terraform_codegen_dir: Path = Field(default=Path("./data/terraform/codegen"))
    terraform_module_registry_dir: Path = Field(default=Path("./terraform/modules"))
    terraform_drift_scan_period_seconds: int = Field(default=3600)
    terraform_artifact_bucket: str = Field(default="aqp-terraform")

    # --- HCP Terraform (remote workspaces) ---
    # When ``terraform_state_backend == "hcp"`` runs go through the HCP
    # HTTP API (workspaces / runs / plans / state-versions). Uses the
    # ``hcp_client.HcpClient`` thin httpx wrapper — no python-terrasnek
    # dep so cold installs without HCP credentials still boot cleanly.
    hcp_token: str = Field(default="")
    hcp_organization: str = Field(default="")
    hcp_api_url: str = Field(default="https://app.terraform.io/api/v2")

    # --- HashiCorp Vault (alt. secret store) ---
    vault_addr: str = Field(default="")
    vault_namespace: str = Field(default="")
    vault_mount: str = Field(default="secret")
    vault_role_id: str = Field(default="")
    vault_secret_id: str = Field(default="")

    # --- Azure cloud anchors (Key Vault + AKS + storage) ---
    azure_tenant_id: str = Field(default="")
    azure_subscription_id: str = Field(default="")
    azure_keyvault_url: str = Field(default="")
    azure_aks_cluster_name: str = Field(default="")
    azure_resource_group: str = Field(default="")
    azure_location: str = Field(default="eastus")

    # --- AWS cloud anchors (Secrets Manager + EKS + S3) ---
    aws_region: str = Field(default="")
    aws_account_id: str = Field(default="")
    aws_secretsmanager_prefix: str = Field(default="aqp/")
    aws_eks_cluster_name: str = Field(default="")

    # --- GCP cloud anchors (Secret Manager + GKE + GCS) ---
    gcp_project_id: str = Field(default="")
    gcp_region: str = Field(default="")
    gcp_secret_prefix: str = Field(default="aqp-")
    gcp_gke_cluster_name: str = Field(default="")

    # --- Pod-level ops (Phase 1 — K8s/Docker SDK extension) ---
    # Docker SDK base URL override (defaults to ``docker.from_env()``).
    # On Linux this is typically ``unix:///var/run/docker.sock``; on
    # Windows ``npipe:////./pipe/docker_engine``. Leave empty to inherit
    # ``DOCKER_HOST`` via the SDK's standard discovery.
    docker_sdk_base_url: str = Field(default="")
    # Per-request timeout the Docker SDK client uses for HTTP calls.
    docker_sdk_timeout: int = Field(default=60)
    # Disable ``Accept-Encoding: gzip,deflate`` on the SDK's underlying
    # requests session. The default ``True`` mirrors the documented
    # gigabyte-tarball fix (without it ``get_archive`` saturates CPU on
    # large pod-archive pulls).
    docker_sdk_disable_compression: bool = Field(default=True)
    # Maximum wall-clock seconds a single ``stream_pod_logs`` call is
    # allowed to run before the route hard-closes the upstream watch.
    # The frontend kill-switch / nav can still re-attach.
    k8s_pod_log_max_seconds: int = Field(default=600)
    # Maximum line count per ``stream_pod_logs`` batch (back-pressure).
    k8s_pod_log_max_lines: int = Field(default=10000)
    # Default deadline for ``exec_in_pod`` when no per-call timeout is
    # passed (covers a single Celery / agent command).
    k8s_exec_default_timeout: int = Field(default=120)

    # --- Codebase MCP (Phase 2) -------------------------------------------
    # Root the codebase MCP is allowed to read. Defaults to the process
    # CWD when empty so local dev / CI just works. In docker images set
    # this to the in-container repo mount (``/workspace/aqp`` etc).
    codebase_workspace_root: str = Field(default="")
    # Optional override for the ripgrep binary; empty means
    # ``shutil.which('rg')`` is used.
    codebase_ripgrep_path: str = Field(default="")
    # Extra secret globs (CSV) to merge with the default deny-list in
    # :mod:`aqp.codebase.mcp.policy`.
    codebase_secret_globs: str = Field(default="")
    # Maximum file size (in KB) the codebase indexer will read in a
    # single pass. Larger files are skipped to keep tool latency
    # bounded (the agent can use ``codebase.search`` instead).
    codebase_max_file_kb: int = Field(default=1024)

    # --- SERA (Phase 2.5, opt-in code provider) ---------------------------
    # OpenAI-compatible endpoint for the Ai2 SERA-32B / SERA-14B code
    # model. Two paths today: ``sera --modal`` (Modal-hosted, the
    # easiest), or ``deploy-sera --model allenai/SERA-32B``
    # (self-hosted vLLM). The provider entry in
    # ``aqp/llm/providers/catalog.py`` routes through LiteLLM's
    # ``openai/`` adapter pointed at this URL.
    sera_enabled: bool = Field(default=False)
    sera_endpoint: str = Field(default="")
    sera_api_key: str = Field(default="")
    sera_model: str = Field(default="allenai/SERA-32B")

    # --- pgvector control plane (Phase 3) ---------------------------------
    # Default embedding dimension matches BGE-M3 (and the
    # ``rag_chunks.embedding`` column type set by alembic 0045). Other
    # embedding models record their own dim via the ``embedding_model``
    # discriminator column on each row.
    pgvector_dim: int = Field(default=1024)
    pgvector_hnsw_m: int = Field(default=16)
    pgvector_hnsw_ef_construction: int = Field(default=64)
    # Per-corpus backend overrides. Format: ``corpus=backend`` CSV,
    # e.g. ``code_chunks=pgvector,bars_daily=redis``. Empty means
    # every corpus uses ``settings.rag_backend_default``.
    rag_backend_default: str = Field(default="redis")  # redis | pgvector | dual
    rag_backend_overrides: str = Field(default="code_chunks=pgvector")

    # --- Agent stall watchdog (Phase 5) -----------------------------------
    # ``agent_runs_v2`` rows older than this with ``status='running'`` and
    # no recent ``agent_run_steps`` rows get marked halted by the
    # watchdog Celery beat task. Rows that are ``status='pending'``
    # longer than ``2 * agent_stall_threshold_seconds`` are also halted.
    agent_stall_threshold_seconds: int = Field(default=300)
    agent_watchdog_enabled: bool = Field(default=True)
    agent_watchdog_period_seconds: int = Field(default=60)

    # --- Orchestration control plane (additive refactor, Phase 0-6) -------
    # All knobs default to ``False`` so the new ``WorkflowRuntime`` +
    # ``OrchestrationAdapter`` machinery stays dormant until an operator
    # opts in. Existing builders / runtimes / routes keep their current
    # behaviour with every flag below set to ``False``.
    #
    # ``orchestration_studio_enabled`` gates the new ``/workflows`` API
    #   surface and the Vite studio routes (Phase 5).
    # ``orchestration_crew_adapter_enabled`` allows the ``CrewProcessAdapter``
    #   to register; CrewAI stays imported lazily so cold installs without
    #   the dep still boot (Phase 2).
    # ``orchestration_fusion_enabled`` activates the optional
    #   ``build_dialectical_with_fusion_graph`` builder and the
    #   ``SignalFusionAdapter`` / ``WeightCentricExecutionAdapter`` (Phase 4).
    # ``orchestration_schedule_enabled`` activates the Celery beat entry
    #   for the ``AutomationScheduleAdapter`` (Phase 3).
    # ``orchestration_workflow_versioning_enabled`` allows the workflow
    #   spec registry to snapshot into ``workflow_spec_versions`` (Phase 5).
    # ``orchestration_kill_propagation_enabled`` extends the watchdog +
    #   ``KillSwitch`` UI to fan halts out into in-flight ``WorkflowRun``
    #   rows (Phase 6).
    orchestration_studio_enabled: bool = Field(default=False)
    orchestration_crew_adapter_enabled: bool = Field(default=False)
    orchestration_fusion_enabled: bool = Field(default=False)
    orchestration_schedule_enabled: bool = Field(default=False)
    orchestration_workflow_versioning_enabled: bool = Field(default=False)
    orchestration_kill_propagation_enabled: bool = Field(default=False)
    # Default max debate rounds for ``DialecticalDebateAdapter`` /
    # ``build_dialectical_debate_graph``. The runtime enforces the cap
    # so a Bull/Bear loop cannot run unbounded even if a spec forgets
    # to set its own.
    orchestration_max_debate_rounds: int = Field(default=2)
    # Per-node halt check timeout used by ``WorkflowRuntime`` between
    # adapter transitions. Kept short so a flipped kill switch is
    # observed inside the SLA from ``docs/orchestration-refactor-rollout.md``.
    orchestration_halt_check_timeout_seconds: float = Field(default=1.0)

    # --- Assistant Engine (additive layer on top of the orchestration
    # control plane). All knobs default to ``False`` / ``"blocked"`` so
    # the new ``AssistantRuntime`` machinery stays dormant until an
    # operator opts in. Existing routes/tasks keep their behaviour.
    #
    # ``assistant_engine_enabled`` gates the new ``/assistants`` REST
    #   surface, the Vite ``/assistants`` route + drawer wiring, and
    #   the ``persist_spec`` write-through into ``assistant_spec_versions``.
    # ``assistant_engine_versioning_enabled`` enables the immutable
    #   hash-locked snapshot persistence (parallel to
    #   ``orchestration_workflow_versioning_enabled``).
    # ``assistant_sandbox_backend`` selects the execution backend for
    #   :class:`aqp.assistants.sandbox.AssistantSandbox`. Default
    #   ``"blocked"`` refuses to execute generated commands; flipping
    #   to ``"docker"`` / ``"microvm"`` (future) is the explicit
    #   opt-in. Never let an LLM-routed flow flip this.
    # ``assistant_max_rounds`` caps debate-style assistant workflows
    #   the same way ``orchestration_max_debate_rounds`` caps the
    #   workflow studio.
    assistant_engine_enabled: bool = Field(default=False)
    assistant_engine_versioning_enabled: bool = Field(default=False)
    assistant_sandbox_backend: str = Field(default="blocked")
    assistant_max_rounds: int = Field(default=4)
    assistant_halt_check_timeout_seconds: float = Field(default=1.0)

    # --- Streaming producers ---
    streaming_producers_namespace: str = Field(default="data-services")

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
    iceberg_rest_credential: str = Field(default="")
    iceberg_rest_token: str = Field(default="")
    iceberg_rest_oauth2_server_uri: str = Field(default="")
    iceberg_rest_scope: str = Field(default="")
    iceberg_rest_extra_properties_json: str = Field(default="")
    iceberg_catalog_name: str = Field(default="aqp")
    iceberg_warehouse: Path = Field(default=Path("./data/iceberg"))
    iceberg_staging_dir: Path = Field(default=Path("./data/iceberg-staging"))
    iceberg_namespace_default: str = Field(default="aqp")
    iceberg_s3_warehouse: str = Field(default="")
    iceberg_max_rows_per_dataset: int = Field(default=5_000_000)
    iceberg_max_files_per_dataset: int = Field(default=2000)
    iceberg_health_check_timeout_seconds: float = Field(default=5.0)
    iceberg_workspace_partition_enabled: bool = Field(default=True)

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

    # --- Data engine + compute backends ---
    compute_backend_default: str = Field(default="auto")
    compute_local_to_dask_rows: int = Field(default=1_000_000)
    compute_local_to_ray_rows: int = Field(default=25_000_000)
    compute_local_to_dask_bytes: int = Field(default=256 * 1024 * 1024)
    compute_local_to_ray_bytes: int = Field(default=8 * 1024 * 1024 * 1024)

    dask_scheduler_address: str = Field(default="")
    dask_n_workers: int = Field(default=2)
    dask_threads_per_worker: int = Field(default=2)
    ray_init_kwargs_json: str = Field(default="")

    engine_default_chunk_rows: int = Field(default=50_000)
    engine_max_concurrent_pipelines: int = Field(default=2)
    engine_pipeline_timeout_seconds: int = Field(default=3600)

    # --- Source library defaults ---
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

    # --- Profile cache ---
    profile_cache_ttl_seconds: int = Field(default=3600)
    profile_cache_prefix: str = Field(default="aqp:profile")
    profile_topk: int = Field(default=10)
    profile_distinct_sample_rows: int = Field(default=200_000)
    profile_default_engine: str = Field(default="auto")

    # --- Entity registry ---
    entity_extraction_enabled: bool = Field(default=True)
    entity_llm_enrichment_enabled: bool = Field(default=False)
    entity_llm_provider: str = Field(default="")
    entity_llm_model: str = Field(default="")
    entity_max_neighbors: int = Field(default=64)
    entity_dedup_similarity_threshold: float = Field(default=0.85)

    # --- Dagster code location ---
    dagster_home: Path = Field(default=Path("./data/dagster_home"))
    dagster_grpc_host: str = Field(default="0.0.0.0")
    dagster_grpc_port: int = Field(default=4000)
    dagster_webserver_url: str = Field(default="")
    dagster_graphql_url: str = Field(default="")
    dagster_code_location: str = Field(default="aqp")
    dagster_module_path: str = Field(default="aqp.dagster.definitions")
    aqp_api_url_internal: str = Field(default="http://api.aqp.svc.cluster.local:8000")
    aqp_api_token: str = Field(default="")

    # --- DataHub bidirectional sync ---
    datahub_sync_enabled: bool = Field(default=False)
    datahub_sync_direction: str = Field(default="push")
    datahub_sync_interval_seconds: int = Field(default=900)
    datahub_platform: str = Field(default="iceberg")
    datahub_platform_instance: str = Field(default="agentic-quant-platform")
    datahub_external_platforms: str = Field(default="")

    # --- Airbyte hybrid data fabric ---
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

    # --- dbt foundation ---
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
        "visualization_cache_dir",
        "visualization_bundle_dir",
        "bootstrap_state_dir",
        "terraform_workspaces_dir",
        "terraform_plugin_cache_dir",
        "terraform_codegen_dir",
        "terraform_module_registry_dir",
    )
    @classmethod
    def _coerce_path(cls, v: Path | str) -> Path:
        return Path(v).expanduser().resolve()

    @property
    def datahub_external_platform_list(self) -> list[str]:
        return [s.strip() for s in self.datahub_external_platforms.split(",") if s.strip()]

    @property
    def ray_init_kwargs(self) -> dict[str, object]:
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
    def local_ingest_path_map_pairs(self) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for raw in self.local_ingest_path_map.split(","):
            entry = raw.strip()
            if not entry:
                continue
            if "=>" in entry:
                left, right = entry.split("=>", 1)
            elif "|" in entry:
                left, right = entry.split("|", 1)
            else:
                continue
            host = left.strip()
            container = right.strip()
            if host and container:
                pairs.append((host, container))
        return pairs

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
        """Return the canonical FinOps tag map for any cloud-bound resource."""
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


__all__ = ["Settings", "get_settings", "settings"]
