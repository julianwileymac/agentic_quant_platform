# aqp_ratelimit — INDEX

| Path | Purpose |
| --- | --- |
| `src/aqp_ratelimit/strategies/base.py` | `IngestionRateLimitStrategy` ABC + `IngestionRateLimitMeta` metaclass. Mirrors `TenancyStrategy`. |
| `src/aqp_ratelimit/strategies/redis_token_bucket.py` | Canonical Redis-backed token-bucket strategy. Loads `lua/token_bucket.lua` once, invokes via `EVALSHA`. |
| `src/aqp_ratelimit/strategies/in_memory.py` | Process-local strategy for tests + offline laptops. |
| `src/aqp_ratelimit/strategies/per_agent.py` | Dual-debit for `MCPToolContext.actor_kind="agent"` (root AGENTS.md rule 54). |
| `src/aqp_ratelimit/strategies/replay_cache.py` | VCR.py-style cassette replay, zero quota burn. |
| `src/aqp_ratelimit/client.py` | Sync + async Python clients used by Fetchers, Dagster sensors, CLI. |
| `src/aqp_ratelimit/factory.py` | Singleton strategy resolver mirroring `TenancyStrategyFactory`. |
| `src/aqp_ratelimit/models.py` | Pydantic `Decision`, `ReserveOutcome`, `PolicyDescriptor`, `KeyDescriptor`. |
| `src/aqp_ratelimit/bridges/agent_bridge.py` | Reads `MCPToolContext.actor_kind` and dual-debits per-agent + per-user. |
| `lua/token_bucket.lua` | Verbatim Redis token-bucket pattern (blueprint §8.2). |
| `lua/reserve.lua` | Multi-token preflight reservation with TTL release. |
| `go-rls/cmd/aqp-rls/main.go` | Standalone Go binary; gRPC `Check`/`Reserve`/`Release` + REST `/v1/status/{key_id}` + Prometheus `/metrics`. |
| `go-rls/proto/ratelimit.proto` | Protobuf contract; the Python client uses the generated stubs. |
| `envoy/bootstrap.yaml` | Envoy v3 bootstrap; ext_authz + ratelimit filter. |
| `envoy/descriptors.yaml` | Descriptor → policy mapping for HTTP request paths. |
| `api/routes/ratelimit.py` | REST: `GET /me/ratelimit/status`, `POST /me/keys`, `DELETE /me/keys/{id}`. |
| `tasks/refresh_policy_cache.py` | Celery beat task syncing `rl_policies` → Redis policy cache. |
| `tasks/ledger_export.py` | Nightly `rl_ledger` → S3 export for audit. |
| `configs/policies/*.yaml` | Per-vendor policy templates (Polygon, Databento, Alpaca, IEX, ...). |
| `../aqp/persistence/models_ratelimit.py` | ORM: `RateLimitPolicy`, `RateLimitKey`, `RateLimitLedger`, `UserTier`, `TemplateCatalog`, `AuditLog`. |
| `../aqp/data/mcp/tools/ratelimit.py` | 4 MCP tools: `data.ratelimit.status`/`reserve`/`policy.list`/`policy.update`. |
| `../alembic/versions/0066_rl_policies.py` | Creates `rl_policies` table. |
| `../alembic/versions/0067_rl_keys.py` | Creates `rl_keys` + adds to RLS_TABLES. |
| `../alembic/versions/0068_rl_ledger.py` | Creates `rl_ledger` partitioned by RANGE on `ts`. |
| `../alembic/versions/0069_user_tiers_template_catalog_audit.py` | Creates `user_tiers`, `template_catalog`, `audit_log` (hash-chain). |
