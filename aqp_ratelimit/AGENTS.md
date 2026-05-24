# AGENTS.md

Agent contract for `aqp_ratelimit`.

## Purpose

This boundary owns the AQP rate-limit accounting subsystem: the
hash-locked policies + keys + ledger that meter every outbound
vendor API call by **(user_id, service, key_id)**, the Redis-backed
Lua token-bucket atomic counters, the standalone Go Rate-Limit
Service ([`go-rls/`](go-rls/)) that speaks gRPC + REST + Prometheus,
the Envoy forward-proxy descriptor filter ([`envoy/`](envoy/)) that
intercepts HTTP egress from connector + kernel + agent pods, the
[`IngestionRateLimitStrategy`](src/aqp_ratelimit/strategies/base.py)
ABC + [`IngestionRateLimitMeta`](src/aqp_ratelimit/strategies/base.py)
metaclass that lets every strategy self-register, the content-
addressable [`replay_cache/`](src/aqp_ratelimit/replay_cache/) that
shields backtests from ever burning vendor quota on already-seen
responses, and the [`data.ratelimit.*`](../aqp/data/mcp/tools/ratelimit.py)
DataMCP tool surface that lets agents inspect (but not silently
override) the quota state.

The boundary also owns the matching Celery task wrapper
([`tasks/`](tasks/)), the FastAPI router ([`api/routes/`](api/routes/)),
the policy YAML library ([`configs/`](configs/)), and the test
suite ([`tests/`](tests/)).

## Hard Boundaries

1. **Every concrete `IngestionRateLimitStrategy` registers via the
   [`IngestionRateLimitMeta`](src/aqp_ratelimit/strategies/base.py)
   metaclass.** Set ``strategy_kind`` (one of `redis_token_bucket`,
   `in_memory`, `leaky_bucket`, `per_agent`, `replay_cache`) and
   `strategy_alias`. The metaclass calls
   :func:`aqp.core.registry.register` automatically. Don't decorate
   with `@register` manually.
2. **All bucket reads / decrements go through the active strategy.**
   Never `HMGET`/`HSET` the Redis bucket key directly outside
   [`strategies/redis_token_bucket.py`](src/aqp_ratelimit/strategies/redis_token_bucket.py).
   The Lua atomicity contract assumes it owns the key namespace
   `aqp:rl:{user_id}:{service}:{key_id}`. Bypassing it creates
   race conditions that double-spend the user's vendor budget.
3. **`rl_policies`, `rl_keys`, `rl_ledger`, `user_tiers`,
   `template_catalog`, `audit_log` are workspace-scoped + RLS-
   protected** and registered in
   [`aqp.tenancy.rls_policies.RLS_TABLES`](../aqp/tenancy/rls_policies.py).
   Migrations 0066-0069 are immutable once shipped (root
   AGENTS.md rule 6).
4. **Mutating MCP tools require step-up MFA.** Both
   `data.ratelimit.reserve` and `data.ratelimit.policy.update`
   set `mutates=True`; the matching routes attach
   `Depends(require_step_up(max_age_seconds=180))` per root
   AGENTS.md rule 52.
5. **Per-agent buckets dual-debit alongside per-user buckets.**
   The `MCPToolContext.actor_kind="agent"` (root AGENTS.md rule 54)
   triggers a second debit against the agent's bucket through
   [`PerAgentStrategy`](src/aqp_ratelimit/strategies/per_agent.py).
   An autonomous agent can never spend the user's budget without
   also drawing down its own ceiling.
6. **The Lua script is the canonical token-bucket implementation.**
   Loaded once via `SCRIPT LOAD` and invoked via `EVALSHA` so the
   rate check sits on the synchronous request path without adding
   meaningful delay at high QPS. Don't reimplement bucket math in
   Python or Go — call the script.
7. **The replay cache shields backtests, never live trading.**
   When `AQP_RATELIMIT_REPLAY_MODE=replay`, cache misses raise
   (VCR.py "none" semantics) so a backtest that would silently
   burn live quota fails fast.

## Where Changes Go

- New strategy kind: subclass
  [`IngestionRateLimitStrategy`](src/aqp_ratelimit/strategies/base.py)
  under [`strategies/`](src/aqp_ratelimit/strategies/) and set
  `strategy_kind` + `strategy_alias`. The metaclass auto-registers.
- New Lua script: drop in [`lua/`](lua/), load + call via
  [`client.py`](src/aqp_ratelimit/client.py).
- New Go handler: extend
  [`go-rls/internal/handlers/`](go-rls/internal/handlers/); regenerate
  the protobuf stubs from [`go-rls/proto/`](go-rls/proto/).
- New Envoy filter / rule: edit
  [`envoy/descriptors.yaml`](envoy/descriptors.yaml).
- New MCP tool: append to
  [`../aqp/data/mcp/tools/ratelimit.py`](../aqp/data/mcp/tools/ratelimit.py)
  (the MCP tool registry lives in the monolith so the bridge
  auto-installs it into `TOOL_REGISTRY`).
- New REST surface: extend
  [`api/routes/ratelimit.py`](api/routes/ratelimit.py).
- New policy template: drop in [`configs/policies/`](configs/policies/).
- Tests: mirror the source path under [`tests/`](tests/).
- Persistence models for `rl_policies` / `rl_keys` / `rl_ledger`
  / `user_tiers` / `template_catalog` / `audit_log` stay in the
  monolith ORM at
  [`../aqp/persistence/models_ratelimit.py`](../aqp/persistence/models_ratelimit.py)
  — this package depends on those rows being there.

## Dependency rules

- This package depends on the monolith for: `iceberg_catalog`
  (when shipping cassette-pinned cache to Iceberg cold storage),
  `LedgerWriter`, `RequestContext`, ORM models, `_progress.emit`,
  `MetadataCache`. No reverse dependency (`aqp.*` MUST NOT
  import `aqp_ratelimit.*` except through the public clients in
  [`src/aqp_ratelimit/client.py`](src/aqp_ratelimit/client.py)).
- The Go RLS binary depends only on Redis + Prometheus. It does
  not import Python; the contract is the protobuf in
  [`go-rls/proto/`](go-rls/proto/).
- Optional: Envoy is a deployment-time component, not a Python
  dependency. The package ships YAML; the operator runs Envoy
  side-by-side with the connector pods.

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
cd go-rls && go test ./...
```
