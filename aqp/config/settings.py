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

from pydantic import AliasChoices, Field, field_validator
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
    # See aqp_docs/docs/concepts/identity/msal-entra-setup.md for the full app-reg walkthrough.
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
    #
    # The Pydantic ``validation_alias`` accepts both the canonical
    # ``AQP_AUTH_MSAL_B2B_ENABLED`` env var and the legacy
    # ``AQP_MSAL_B2B_ENABLED`` documented in older ``.env.example``
    # files so deployments don't silently regress to the default.
    auth_msal_b2b_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "AQP_AUTH_MSAL_B2B_ENABLED",
            "AQP_MSAL_B2B_ENABLED",
        ),
    )
    auth_msal_known_tenants: str = Field(default="")  # CSV of tenant_ids
    # --- AQP staff Entra tenant (Workstream "Entra internal tenant") ---
    # Pinned to a single Entra tenant so AQP staff bypass the B2B
    # approval wizard. Tokens whose ``iss`` claim matches
    # ``https://login.microsoftonline.com/{auth_msal_internal_tenant_id}/v2.0``
    # are routed to MsalEntraIdentityProvider before any other provider.
    # Customer-tenant tokens still flow through the EntraTenantLink B2B
    # path (rule 44).
    #
    # See docs/plans/entra-internal-tenant-rollout.md and
    # aqp_platform/terraform/modules/aqp_entra_directory/.
    auth_msal_internal_tenant_id: str = Field(default="")
    auth_msal_internal_app_id: str = Field(default="")
    auth_msal_internal_authority: str = Field(default="")
    # Audience the manage API expects on staff access tokens.
    auth_msal_internal_audience: str = Field(default="api://aqp-manage-api")
    # Provider chain priority. Lower = earlier; MSAL=100 / Auth0=200 /
    # local=1000 is the canonical order. Set to a high value (9999) to
    # demote MSAL during a rollback (see rollout plan §5.1).
    auth_msal_priority: int = Field(default=100)
    # Name of the role claim minted by the manage API. The Entra
    # default is ``roles``; override only if a custom claims-mapping
    # policy is in place.
    auth_msal_app_role_claim: str = Field(default="roles")
    # The display-name list of CA policies the operator promises
    # exist out-of-band (mirrors the Terraform module's
    # ``ca_policy_references`` input). The verify_entra_login helper
    # reads this to confirm at smoke-test time.
    auth_msal_required_ca_policies: str = Field(
        default="AQP-Admins-MFA-Required,AQP-Block-Risky-Sign-Ins"
    )
    # Pre-seeded internal-tenant link metadata. The seed script reads
    # these to upsert the canonical entra_tenant_links row with
    # ``meta.kind = 'internal'`` (rule 44).
    auth_msal_internal_tenant_domain: str = Field(
        default="wiley-tech.onmicrosoft.com",
        description=(
            "Primary domain of the AQP staff Entra tenant. Echoed in "
            "EntraTenantLink.primary_domain so the audit trail shows "
            "the human-readable handle alongside the GUID."
        ),
    )
    auth_msal_internal_display_name: str = Field(
        default="AQP Internal (wiley-tech)",
    )
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
        default="./aqp_platform/configs/deployment/topology.yaml"
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
    # --- MCP RFC 9728 + RFC 8707 conformance (Workstream E) ---
    # The 2025-11-25 MCP authorization spec mandates that each MCP
    # server publish a Protected Resource Metadata document (RFC 9728)
    # and validate that incoming access tokens carry the server's
    # canonical URI in their ``aud`` (or ``resource``) claim (RFC 8707).
    # ``mcp_data_canonical_uri`` and ``mcp_codebase_canonical_uri`` are
    # the canonical URIs the well-known endpoint advertises and the
    # audience validator enforces. Empty defaults to the backend's
    # external URL plus the matching ``/mcp/*`` path; production
    # deployments SHOULD set them explicitly.
    mcp_data_canonical_uri: str = Field(default="")
    mcp_codebase_canonical_uri: str = Field(default="")
    # ``mcp_docs_canonical_uri`` is the third MCP audience claim, scoped
    # to the docs site MCP Worker at https://docs.aqp.fund/mcp. The
    # Worker lives outside the cluster (Cloudflare Pages); the AQP
    # backend still publishes the Protected Resource Metadata at
    # /.well-known/oauth-protected-resource/mcp-docs and validates the
    # audience here so in-cluster callers that delegate to the docs
    # server get the same RFC 9728 + 8707 guarantees as data + codebase.
    # See aqp_docs/workers/mcp/index.ts and aqp_docs/concepts/data/data-mcp.
    mcp_docs_canonical_uri: str = Field(default="")
    # ``mcp_ml_canonical_uri`` is the fourth MCP audience claim, scoped
    # to the dedicated MLOps MCP server at ``/mcp/ml`` (see
    # :mod:`aqp.ml_mcp`). Audience-bound tokens minted by the AS MUST
    # include this URI in ``aud`` / ``resource`` for ``data.ml.*``
    # tool calls to succeed under
    # ``mcp_require_rfc8707="strict"``. Defaults to empty; production
    # deployments set it to e.g. ``https://api.aqp.fund/mcp/ml``.
    mcp_ml_canonical_uri: str = Field(default="")
    # ``mcp_ml_url`` — internal URL of the MLOps MCP server. Resolved
    # via the topology service (Hard Rule 47) when set, otherwise
    # defaults to the backend's external URL plus ``/mcp/ml``.
    mcp_ml_url: str = Field(default="")
    # --- MLOps service knobs (initial slice) ---
    # ``ml_cache_max_entries`` / ``ml_cache_max_vram_bytes`` are the
    # LRU + memory budgets the in-process :class:`CacheHandler` honours.
    # Defaults are conservative — production GPU pods MAY scale them.
    ml_cache_max_entries: int = Field(default=16)
    ml_cache_max_vram_bytes: int = Field(default=32 * 1024**3)
    # Continuous-batching scheduler defaults. ``max_batch_size`` is
    # the upper bound on a single fan-in; ``max_wait_ms`` is the
    # latency budget the scheduler grants before flushing a partial
    # batch. The same defaults appear in
    # :class:`aqp_models.handlers.ServeHandler`.
    ml_serving_max_batch_size: int = Field(default=64)
    ml_serving_max_wait_ms: int = Field(default=25)
    # Default z-score threshold used by
    # :class:`aqp_models.rules.OODGuard`. The skill runtime gates each
    # step against this before invoking the underlying interface.
    ml_ood_zscore_threshold: float = Field(default=4.0)
    # Operator can force the HuggingFace + TorchHub adapters into a
    # fully offline mode (only cached snapshots) by flipping these to
    # ``true`` (e.g., in an air-gapped deployment).
    ml_hf_hub_offline: bool = Field(default=False)
    ml_torchhub_offline: bool = Field(default=False)
    # --- Docs freshness watchdog (Phase 6 of the docs migration) ---
    # The Celery beat task ``aqp.tasks.docs_freshness_tasks.scan_stale_pages``
    # opens a GitHub Issue per page whose ``last_reviewed`` frontmatter
    # is more than ``docs_freshness_threshold_days`` old. Defaults to
    # 180 days, the value documented in
    # ``aqp_docs/docs/intro/conventions.md``.
    docs_freshness_threshold_days: int = Field(default=180)
    # ``docs_github_repo`` — the slug used by the docs-freshness +
    # feedback workers when opening issues. Defaults to the main
    # repo; production deployments MAY override (e.g., when running
    # the docs site against a fork during a migration).
    docs_github_repo: str = Field(default="julianwileymac/agentic_quant_platform")
    # Beat cadence for the docs freshness scan. Defaults to one
    # week (seconds). The scan itself is cheap (walks the docs
    # tree + parses frontmatter); the per-page GitHub Issue calls
    # are de-duped at the GitHub side via the labelling scheme.
    docs_freshness_scan_period_seconds: int = Field(default=7 * 24 * 3600)
    # ``off`` skips audience enforcement (rollout default). ``permissive``
    # logs would-be denies + tags the OTEL span without rejecting.
    # ``strict`` returns 401 with the RFC 9728 ``WWW-Authenticate``
    # header when the token audience does not include the MCP
    # canonical URI. Flip to ``strict`` after the dashboard shows
    # zero would-be denies for 24 h.
    mcp_require_rfc8707: str = Field(default="off")  # off | permissive | strict
    # Backend external URL used by ``aqp/api/well_known.py`` as a
    # fallback when neither MCP canonical URI is explicitly set. Empty
    # in pre-production deployments. Mirrors the existing
    # ``auth_login_callback`` shape.
    backend_external_url: str = Field(default="")
    # --- Lineage Ed25519 signing (Workstream C) ---
    # When enabled, every ``transform_vertex`` row in the bipartite
    # lineage ledger carries an Ed25519 signature over the canonical
    # encoding of (job_name || run_id || code_version || sorted_params
    # || sorted_input_hashes || sorted_output_hashes). Per-actor keys
    # resolve through :class:`CredentialResolver` (rule 26); the
    # archived public-key index lives in ``lineage_signing_key_archive``.
    # ``off`` short-circuits (default). ``permissive`` attempts to sign
    # and falls back to an empty signature on failure. ``strict``
    # raises on any signing failure.
    lineage_signing_enabled: bool = Field(default=False)
    lineage_signing_mode: str = Field(default="permissive")  # off | permissive | strict
    # --- Bipartite lineage graph (Workstream A) ---
    # Enables the BipartiteGraphObserver that dual-writes every
    # LineageEvent into the new dataset_vertex / transform_vertex /
    # edge tables. The legacy ``data_lineage_events`` flat log keeps
    # writing unchanged; the new graph is purely additive.
    lineage_graph_enabled: bool = Field(default=False)
    # --- OpenLineage / Marquez relay (Workstream B) ---
    lineage_openlineage_relay_enabled: bool = Field(default=False)
    lineage_openlineage_marquez_url: str = Field(default="")
    lineage_openlineage_namespace: str = Field(default="aqp")
    lineage_openlineage_relay_batch: int = Field(default=200)
    # --- Multi-tenant TenancyStrategy (Workstream F) ---
    # The default isolation strategy when no per-org override is set on
    # the :class:`Organization.tenancy_strategy` column. The rollout
    # default is ``shared_schema_rls`` (B2C pool). Production typically
    # flips to ``hybrid`` once enterprise customers land.
    tenancy_default_strategy: str = Field(default="shared_schema_rls")
    # ``off`` skips RLS enforcement at the app role level (the policies
    # are still installed but the runtime connects as a BYPASSRLS role
    # so existing routes keep working). ``permissive`` connects as the
    # non-BYPASSRLS ``app_runtime`` role with logging on
    # ``current_setting('app.current_organization_id', true) IS NULL``
    # accesses. ``strict`` enforces strictly and any code path that
    # forgot to set the GUC raises ``permission_denied``.
    tenancy_rls_enforce: str = Field(default="off")  # off | permissive | strict
    # LRU TTL for the database-per-enterprise engine cache. The cache
    # avoids re-resolving the DSN + re-creating the engine for every
    # session checkout on the same tenant; 30 min (1800 s) is the
    # default — flip lower in dev so DSN rotation propagates faster.
    tenancy_db_per_enterprise_pool_ttl_seconds: int = Field(default=1800)
    # --- Phase 6 §9 — Per-cell data plane (RESTRUCTURING_PLAN.md) ---
    # Dual-write switch. When True, application writes go to BOTH the
    # shared cluster-wide data plane AND the per-cell data plane (the
    # cell resolved from ``RequestContext.cell_id``). Used during the
    # silo-reg backfill window so a tenant can be migrated without
    # downtime: turn this on, backfill historical rows with
    # ``scripts/cells/dual_write_backfill.py``, verify parity, then
    # cut the tenant over by mutating ``tenant_cells.cell_id`` and
    # flipping this flag back off.
    #
    # MUST stay False outside the documented migration window — the
    # dual writes double the write cost and double the audit-row
    # surface area. The Phase 6 runbook
    # ``aqp_docs/docs/how-to/cell-data-plane-migration.md`` is the
    # canonical operating procedure.
    cell_dual_write: bool = Field(default=False)
    # Default cell id for callers that have no request-context-bound
    # cell (Celery beat, scripts/, fast-path bootstrap). Empty falls
    # back to the legacy shared cluster-wide engine. When a non-empty
    # value is set the cell-aware engine cache resolves to the
    # corresponding ``CellDataPlane`` block in ``topology.yaml``.
    cell_default_id: str = Field(default="")
    # --- Phase 7 §10.1 — Audit lake + transparency anchors ---
    # Master switch for the hourly audit-lake flush. When False, the
    # Celery beat task ``aqp.tasks.audit_lake_tasks.flush`` short-
    # circuits and emits a ``skipped`` summary. Operators flip this to
    # True once Iceberg + per-cell MinIO are reachable and at least one
    # transparency sink is configured.
    audit_lake_enabled: bool = Field(default=False)
    # How long each audit-lake segment covers, in minutes. The default
    # 60 matches the hourly Celery beat schedule. Smaller values make
    # for finer-grained replay windows but more anchor submissions.
    audit_lake_segment_minutes: int = Field(default=60)
    # Hourly Celery beat interval for the flush task. Defaults to 3600 s.
    audit_lake_flush_interval_seconds: int = Field(default=3600)
    # Comma-separated list of transparency-anchor sinks to submit to.
    # Valid kinds: ``rekor``, ``qldb``, ``rfc3161``. Empty means anchor
    # is disabled (the segment still flushes to Iceberg).
    audit_transparency_sinks: str = Field(default="")
    # Rekor base URL. Public sigstore by default; operators can point
    # at a private Rekor instance for cells that prohibit Internet egress.
    audit_rekor_url: str = Field(default="https://rekor.sigstore.dev")
    # AWS QLDB ledger name + region (only used when ``qldb`` is in
    # ``audit_transparency_sinks``). Empty means QLDB is disabled.
    audit_qldb_ledger_name: str = Field(default="")
    audit_qldb_region: str = Field(default="")
    # RFC 3161 TSA alias + URL. The alias namespaces the
    # ``CredentialResolver`` lookup so operators can carry multiple TSAs.
    audit_rfc3161_tsa_alias: str = Field(default="default")
    audit_rfc3161_tsa_url: str = Field(default="")
    # --- Per-user external OAuth (Workstream D) ---
    # Toggles the entire user-level OAuth wizard. When false, the
    # ``/me/oauth-connections`` routes 404, the ``UserOAuthTokenStore``
    # is not installed in the resolver chain, and the refresh worker
    # short-circuits. Production deployments flip this on once
    # Vault Transit is up and the per-provider client ids land in
    # ``CredentialResolver``.
    user_oauth_enabled: bool = Field(default=False)
    user_oauth_refresh_window_seconds: int = Field(default=300)
    # Hex-encoded 32-byte key for the LOCAL fallback envelope
    # encryption (used when ``VAULT_ADDR`` isn't set). Generate with
    # ``openssl rand -hex 32``. Empty in production deployments; a
    # warning is logged on every encrypt when this fallback is hit.
    user_oauth_local_key: str = Field(default="")
    # Phase 3a of the AQP control-plane maturation gates the
    # WebSocket first-frame token protocol on this flag. When False
    # (default during the cutover), an unauthenticated WS connection
    # silently degrades to the local-first default user, mirroring
    # the HTTP path's ``current_user`` fallback. When True, WS routes
    # close the socket with code 4001 if the first frame is not a
    # valid ``{"type":"auth","token":"..."}`` payload. Flip to True
    # in production once the frontend has cut over to the new
    # protocol (see ``aqp_client/src/lib/ws/client.ts``).
    ws_auth_required: bool = Field(default=False)
    # Phase 4d of the AQP control-plane maturation gates per-route
    # DPoP (RFC 9449) proof-of-possession enforcement. When True, the
    # ``require_dpop_token`` dependency rejects Bearer-only requests
    # to the highest-value endpoints (terraform apply / destroy,
    # workloads:halt, live trade execute, tenancy invite). Off by
    # default so existing API clients keep working until they migrate
    # to a DPoP-capable client (the SPA via the auth0-fastapi-api SDK
    # mixed-mode handshake, programmatic clients via the Auth0
    # client-credentials grant with a DPoP header).
    dpop_enforcement_enabled: bool = Field(default=False)
    # --- Step-up MFA (AGENTS hard rule 52, RFC 9470) ---
    # Master kill switch for the step-up MFA enforcement deps in
    # :mod:`aqp.api.security_stepup`. Set to ``False`` only as an
    # incident-response break-glass; doing so flips kill-switch and
    # every destructive endpoint into log-only mode.
    auth_step_up_enabled: bool = Field(default=True)
    # Default freshness window in seconds for ``require_step_up`` deps
    # that don't pass an explicit override. 180s is short enough to
    # neutralise stolen session tokens against a destructive op but
    # long enough that operators who just MFA'd to open the dashboard
    # don't get prompted on every halt click. Per-route overrides
    # always win.
    auth_step_up_default_max_age: int = Field(default=180)
    # --- Auth0 Log Streams webhook (AGENTS hard rule 53, Phase 4) ---
    # Shared secret presented by Auth0 in the ``Authorization`` header of
    # custom-webhook log-stream POSTs to ``/_internal/auth0/log-stream``.
    # Must mirror the secret configured in the Auth0 Dashboard
    # (Monitoring -> Streams -> Custom Webhook). Generate via
    # ``openssl rand -hex 32``. Empty disables the webhook (returns 503).
    auth0_log_stream_secret: str = Field(default="")
    # Maximum age in seconds to accept a log-stream payload by
    # ``log_id`` timestamp. Auth0 retries failed deliveries with the
    # same payload; this guards replay attempts beyond the retry
    # window.
    auth0_log_stream_max_age_seconds: int = Field(default=86_400)
    # --- RFC 8693 Token Exchange for delegated agent tokens ---
    # When True, :class:`aqp.auth.token_exchange.TokenExchangeBroker`
    # is allowed to mint delegated tokens for agent runtimes via Auth0
    # Custom Token Exchange Profile ``aqp-agent-delegation``. Off by
    # default so existing agent runtimes that pass the M2M token
    # directly keep working.
    auth_agent_token_exchange_enabled: bool = Field(default=False)
    # M2M client id + secret for the ``aqp-agent-broker`` Auth0 app
    # that is permitted to call the Token Exchange endpoint. Resolved
    # via :class:`aqp.credentials.CredentialResolver` in prod; env vars
    # are the local-dev shortcut.
    auth_agent_broker_client_id: str = Field(default="")
    auth_agent_broker_client_secret: str = Field(default="")
    # Lifetime ceiling (seconds) for minted delegated agent tokens.
    # Auth0 enforces the lower of this and the API record's token TTL.
    auth_agent_delegation_ttl_seconds: int = Field(default=300)
    # AQP-namespaced custom claim prefix injected by the Auth0 Action.
    # See ``aqp_docs/docs/concepts/identity/auth0-actions.md``. Decoupled from the issuer URL so
    # the same Action works against staging / prod tenants without
    # rebuilding the SPA.
    #
    # Canonical namespace as of the refactor is ``https://aqp.internal/``
    # (per ADR 003 — `aqp_docs/docs/architecture/decisions/003-auth0-zero-trust.md`).
    # The legacy ``https://aqp/`` namespace continues to be read for one
    # release via ``auth_claims_namespace_aliases`` so existing tokens
    # validate during the rollout window.
    auth_claims_namespace: str = Field(default="https://aqp.internal/")
    auth_claims_namespace_aliases: list[str] = Field(
        default_factory=lambda: ["https://aqp/"],
        description=(
            "Backward-compatible claim namespaces still honoured by the "
            "JWT validator. Keep ``https://aqp/`` here for one release "
            "after migrating the post-login Action to the canonical "
            "``https://aqp.internal/`` namespace."
        ),
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

    # --- WebSocket replay stream (Phase 3 of the cloud-dash refactor) ---
    # Every ``emit(...)`` from :mod:`aqp.tasks._progress` is dual-written to
    # ``aqp:task:frames:<task_id>`` so a reconnecting WS client can replay
    # what it missed during the disconnect window. The ``maxlen`` cap is
    # approximate (Redis ``MAXLEN ~``); ``ttl_seconds`` is the eventual
    # cleanup floor for streams whose worker exited without calling
    # :func:`aqp.ws.broker.prune_replay_stream`.
    task_replay_maxlen: int = Field(default=10_000)
    task_replay_ttl_seconds: int = Field(default=86_400)

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
    # AGENTS Rule 26 — bootstrap-only credential. Never read this
    # attribute outside `aqp/credentials/`. Production code resolves
    # through `CredentialResolver.resolve(CredentialKey("datahub",
    # "default"))` so the priority chain (M2M > File > Env > bootstrap)
    # wins. The previous public name `datahub_token` was renamed to
    # `bootstrap_datahub_token` in Phase 0 to make every direct read
    # site fail the build (the `_token` suffix is already in the
    # credential-resolver lint deny-list). The env var stays
    # `AQP_DATAHUB_TOKEN` for operational continuity.
    bootstrap_datahub_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AQP_DATAHUB_TOKEN",
            "AQP_BOOTSTRAP_DATAHUB_TOKEN",
        ),
    )
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

    # --- Phase 2 infra services (additive, side-by-side with the legacy
    # rpi_kubernetes-owned shared services). Defaults stay empty so that
    # ``aqp.config.topology_fallback.apply_topology_fallback`` is the only
    # source of populated URLs in Phase 2; downstream code that wants to
    # use these MUST short-circuit on empty values.

    # Redpanda (side-by-side with Strimzi Kafka per plan question 2).
    redpanda_bootstrap: str = Field(default="")
    redpanda_admin_url: str = Field(default="")
    redpanda_schema_registry_url: str = Field(default="")
    redpanda_connect_url: str = Field(default="")

    # QuestDB time-series database.
    questdb_pg_url: str = Field(default="")
    questdb_ilp_url: str = Field(default="")
    questdb_http_url: str = Field(default="")

    # Arize Phoenix (self-hosted LLM/agent/RAG observability).
    phoenix_endpoint: str = Field(default="")
    phoenix_grpc_endpoint: str = Field(default="")
    phoenix_ui_url: str = Field(default="")
    phoenix_project_default: str = Field(default="aqp")

    # Prometheus + Grafana + Loki + Tempo (observability stack).
    prometheus_url: str = Field(default="")
    prometheus_remote_write_url: str = Field(default="")
    grafana_url: str = Field(default="")
    loki_url: str = Field(default="")
    tempo_otlp_url: str = Field(default="")

    # Apache Hudi (additive lakehouse for upsert-heavy partitions per
    # plan section D; Iceberg remains the canonical write path - rule 3).
    hudi_warehouse_url: str = Field(default="")
    hudi_metastore_url: str = Field(default="")
    hudi_namespace_prefix: str = Field(default="aqp_hudi_")

    # AQP control-plane legacy fallback (rpi-k8s-management API).
    # Default ``False`` — AQP no longer reaches into rpi_kubernetes shared
    # services. Only flip to ``True`` for an emergency rollback to the
    # deprecated `rpi-k8s-management` legacy API; the matching k8s
    # Deployment is rollback-only under
    # `aqp_platform/deployments/kubernetes/rollback/legacy-management/`.
    control_plane_legacy_fallback: bool = Field(default=False)

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
    terraform_module_registry_dir: Path = Field(default=Path("./aqp_platform/terraform/modules"))
    terraform_drift_scan_period_seconds: int = Field(default=3600)
    terraform_artifact_bucket: str = Field(default="aqp-terraform")
    # Phase 0.1 (CP maturation) — flip the in-monolith Terraform routes
    # / Celery tasks / MCP tools from in-process execution to brokered
    # HTTP calls against the CP-native TerraformRuntime in
    # ``aqp_control_plane``. Defaults False during rollout. When True,
    # mutating actions are forwarded to ``<aqp_cp>/manage/terraform/*``
    # and the canonical ``terraform_runs`` ledger is filled by the
    # CP-side ``HttpTerraformAuditSink`` posting to
    # ``/_internal/audit/terraform-runs`` on the monolith.
    terraform_use_control_plane: bool = Field(default=False)
    # Audience the monolith expects on the M2M Bearer token attached to
    # ``/_internal/audit/*`` POSTs from the CP. Empty falls back to
    # ``settings.auth_oidc_audience``; production deployments pin a
    # dedicated M2M-only audience so audit traffic stays scoped.
    terraform_audit_ingest_audience: str = Field(default="")

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

    # --- Amazon Bedrock LLM provider (Phase D of AWS hybrid rollout) ----
    # When ``router_complete`` resolves ``provider="bedrock"`` the call
    # routes through LiteLLM's native ``bedrock/`` adapter. The boto3
    # credential chain handles auth (IRSA / EKS Pod Identity / ECS task
    # role / EC2 instance profile / AWS_PROFILE) — there is no AQP
    # ``AQP_BEDROCK_API_KEY`` knob by design (long-term Bedrock API
    # keys are SCP-denied at the org root; see the Sonrai disclosure
    # in the landing-zone module).
    #
    # ``bedrock_region`` falls through to ``aws_region`` then to the
    # ``AWS_REGION`` env var. ``bedrock_guardrail_id`` + ``_version``
    # are optional — when set, ``router_complete`` injects them as
    # ``guardrailConfig`` so every Bedrock InvokeModel call passes
    # through the configured Bedrock Guardrail.
    bedrock_region: str = Field(default="")
    bedrock_guardrail_id: str = Field(default="")
    bedrock_guardrail_version: str = Field(default="")

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
    # observed inside the SLA from ``aqp_docs/docs/concepts/agentic/orchestration-refactor-rollout.md``.
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

    # --- Data Lab (four-mode GraphSpec workspace) ---
    #
    # ``aqp_lab_enabled`` is the master feature flag for the Data Lab
    # routes (REST + WebSocket) and Celery task surface introduced in
    # the Data Lab implementation. When False, the routes are not
    # mounted on the FastAPI app, the Celery task module is not
    # included, and the Vite frontend hides the /labs/[lab_id]/workspace
    # entry point. Mirrors the assistant_engine_enabled pattern.
    aqp_lab_enabled: bool = Field(default=True)
    aqp_lab_default_queue: str = Field(default="lab.cpu")
    aqp_lab_inline_runs: bool = Field(default=True)
    aqp_lab_snippet_sandbox_tier: str = Field(default="tier1")
    aqp_lab_snippet_timeout_seconds: int = Field(default=300)
    # ``aqp_lab_default_iceberg_namespace`` is the Iceberg namespace the
    # Data Lab's data.iceberg_scan executor uses when the user omits one.
    # Mirrors ``iceberg_namespace_default`` for the Lab's reproducibility
    # contract — runs pin a snapshot id resolved against this namespace
    # when no explicit ns is configured.
    aqp_lab_default_iceberg_namespace: str = Field(default="aqp_silver_equities_bars")
    # ``aqp_lab_executor_images`` maps an executor alias (e.g.
    # ``vbtpro``, ``hftbacktest``, ``torch_gpu``) to the container image
    # digest the snippet runner pulls. The ``code_snapshot`` hash on
    # every LabRun mixes a stable hash of this dict so a replay refuses
    # if the digest no longer exists in the registry.
    aqp_lab_executor_images: dict[str, str] = Field(default_factory=dict)
    # ``aqp_lab_sandbox_runtime`` picks the Tier-2 server-side sandbox
    # for vectorbt-pro / hftbacktest / Numba / GPU snippets. ``none``
    # disables Tier 2 entirely (snippet runner refuses to dispatch
    # heavy workloads); ``gvisor`` wraps the snippet container with the
    # gVisor runtime (``runsc``); ``docker`` is the unsafe fallback for
    # local dev only.
    aqp_lab_sandbox_runtime: str = Field(default="none")
    # ``aqp_lab_pyodide_enabled`` is the frontend feature flag for the
    # Pyodide Tier-1 sandbox (in-browser pure-Python execution). When
    # False, EDA cells fall back to the server-side AnalysisRuntime
    # kernel only. Toggle once Pyodide is bundled into aqp_client.
    aqp_lab_pyodide_enabled: bool = Field(default=False)
    # ``aqp_lab_ray_tune_enabled`` switches the Evaluation sweep
    # controller from the default Celery-group dispatch to a
    # ``ray.tune.Tuner`` job. Falls back to Celery when the Ray cluster
    # is unreachable.
    aqp_lab_ray_tune_enabled: bool = Field(default=False)
    # Phase 3 — DSR safety. The Evaluation mode refuses sweeps that
    # would produce more than ``aqp_lab_max_sweep_trials`` train/test
    # combinations unless the caller passes ``confirm=true``. Default
    # set per plan §3 (warn at 100, refuse >500).
    aqp_lab_max_sweep_trials: int = Field(default=500)
    aqp_lab_warn_sweep_trials: int = Field(default=100)

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
    instance = Settings()
    # Phase 0 infra-expansion: apply topology.yaml fallback for URL fields
    # whose default is still in effect (no AQP_* env override). Failures
    # are logged inside the helper and never break boot.
    try:
        from aqp.config.topology_fallback import apply_topology_fallback

        apply_topology_fallback(instance)
    except Exception:  # noqa: BLE001
        # Topology fallback is best-effort. Any unexpected failure must
        # not prevent the cached singleton from being returned, since
        # half the codebase imports ``settings`` at module load time.
        import logging

        logging.getLogger(__name__).warning(
            "topology fallback failed during get_settings()",
            exc_info=True,
        )
    return instance


settings = get_settings()


__all__ = ["Settings", "get_settings", "settings"]
