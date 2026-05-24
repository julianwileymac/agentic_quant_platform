# aqp-ratelimit

Per-(user, service, key_id) rate-limit accounting for the Agentic Quant
Platform.

## What this is

`aqp_ratelimit/` is the standalone boundary that meters every outbound
vendor API call across the entire AQP stack — Airbyte CDK connectors,
Dagster sensor-gated backfills, Jupyter kernel notebook sessions, agent
ingestion tools. The contract is a 3-tuple **(user_id, service, key_id)**
mapped to a Redis Lua token-bucket counter, fronted by a Go RLS service
speaking gRPC + REST + Prometheus, with an optional Envoy forward-proxy
that intercepts HTTP egress transparently.

## Layout

```
aqp_ratelimit/
├── AGENTS.md
├── README.md
├── INDEX.md
├── pyproject.toml
├── src/aqp_ratelimit/
│   ├── __init__.py
│   ├── client.py                  # sync + async Python clients
│   ├── factory.py                 # singleton strategy resolver
│   ├── exceptions.py
│   ├── models.py                  # pydantic Decision, ReserveOutcome, ...
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py                # IngestionRateLimitStrategy ABC + Meta
│   │   ├── in_memory.py           # tests + offline laptop
│   │   ├── redis_token_bucket.py  # canonical Redis Lua
│   │   ├── per_agent.py           # dual-debit for agent runs (rule 54)
│   │   └── replay_cache.py        # VCR.py-style cassette replay
│   ├── bridges/
│   │   ├── __init__.py
│   │   └── agent_bridge.py        # MCPToolContext.actor_kind=agent
│   └── replay_cache/
│       ├── __init__.py
│       ├── store.py               # S3 content-addressable
│       └── policies.py            # historical / eod / realtime TTL
├── lua/
│   ├── token_bucket.lua           # canonical Lua atomic check
│   ├── reserve.lua                # multi-token preflight reserve
│   └── release.lua                # release reserved tokens on TTL
├── go-rls/
│   ├── go.mod
│   ├── cmd/aqp-rls/main.go
│   ├── internal/server/
│   ├── internal/handlers/
│   ├── internal/redis/
│   └── proto/ratelimit.proto
├── envoy/
│   ├── bootstrap.yaml
│   ├── ratelimit_filter.yaml
│   └── descriptors.yaml
├── tasks/
│   ├── __init__.py
│   ├── refresh_policy_cache.py
│   └── ledger_export.py
├── api/
│   └── routes/
│       ├── __init__.py
│       └── ratelimit.py           # REST: /me/ratelimit/*
├── configs/
│   └── policies/
│       ├── polygon.yaml
│       ├── databento.yaml
│       ├── alpaca.yaml
│       └── ...
└── tests/
    ├── test_strategy_redis.py
    ├── test_strategy_in_memory.py
    ├── test_lua_token_bucket.py
    ├── test_client.py
    └── test_factory.py
```

## Hard boundaries

See [AGENTS.md](AGENTS.md) for the canonical contract.

## Quickstart

```python
from aqp_ratelimit import get_ratelimit_client

client = get_ratelimit_client()
decision = client.check(
    user_id="user_abc",
    service="polygon.aggregates",
    key_id="key_primary",
    n_tokens=1,
)
if not decision.allow:
    raise RuntimeError(
        f"polygon budget exhausted; retry in {decision.retry_after_ms}ms"
    )
```

For partitioned backfills the preflight pattern reserves tokens upfront:

```python
outcome = client.reserve(
    user_id="user_abc",
    service="polygon.aggregates",
    key_id="key_primary",
    n_tokens=240_000,
    ttl_s=3600,
)
if not outcome.allow:
    raise RuntimeError(
        f"this backfill would need {outcome.requested} tokens, "
        f"your monthly budget has {outcome.remaining} remaining"
    )
```

## CLI

```bash
aqp ratelimit status
aqp ratelimit status --service polygon.aggregates --key-id key_primary
aqp keys mint   --service polygon --rps 5 --burst 20 --ttl 30d
aqp keys list
aqp keys rotate --key-id <uuid>
aqp keys revoke --key-id <uuid>
```

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
cd go-rls && go test ./...
```
