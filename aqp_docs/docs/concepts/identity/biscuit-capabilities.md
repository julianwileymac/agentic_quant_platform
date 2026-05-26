---
title: Biscuit capability tokens
description: Phase 5 §8.2 — biscuit capability tokens for capability-attenuated agent → MCP delegation.
sidebar_label: Biscuit capability tokens
---

# Biscuit capability tokens

> Phase 5 §8.2 of
> [RESTRUCTURING_PLAN.md](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md).
> Sits ALONGSIDE the existing
> [`TokenExchangeBroker`](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp/auth/token_exchange.py)
> (Rule 54), not replacing it.

## The problem

`TokenExchangeBroker` mints short-lived JWTs via the
RFC 8693 ``urn:ietf:params:oauth:grant-type:token-exchange`` grant.
The result is a delegated agent JWT that carries every scope the
agent could possibly need:

```
GET /mcp/data/iceberg.read  -- Bearer <delegated-jwt with scopes: data:read data:write data:export>
POST /mcp/data/iceberg.write -- Bearer <same jwt>
```

If the agent is compromised mid-run, the attacker exfiltrates the
JWT and replays it for ANY of those scopes until expiry. The JWT is
broad-by-design — the broker can't know in advance which exact tool
+ arguments the agent will call.

## The Biscuit answer

A biscuit is a capability token with a key property: **anyone can
narrow it (attenuate), no one can widen it**. The minting flow
becomes:

```
user JWT
   │
   ▼
TokenExchangeBroker.exchange()     -> delegated JWT (broad scopes)
   │
   ▼
biscuit.mint_biscuit(jwt, caps)    -> biscuit covering the full
   │                                  capability set for this run
   ▼
agent.attenuate_for_call(...)      -> EXACTLY (tool, args, hash)
   │
   ▼
HTTP POST /mcp/data/iceberg.read
  Authorization: Bearer <jwt>      -- existing path stays
  X-Biscuit: <attenuated-biscuit>  -- new gate
```

A compromised agent that exfiltrates the attenuated biscuit can
ONLY replay the one call that biscuit was minted for. The
attenuated biscuit's chained check fires on any other call:

```
check if capability("data.iceberg.read", "read", "nyse:trades", "<hash>")
```

## AQP integration

The helpers live in [`aqp/auth/biscuit.py`](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp/auth/biscuit.py):

```python
from aqp.auth.biscuit import (
    mint_biscuit, attenuate_for_call, verify_biscuit,
    Capability,
)

# 1. Mint at agent-run boot — derive from the delegated JWT's scopes.
issued = mint_biscuit(
    user_sub=request.user.sub,
    agent_sub="agent_alpha_research_v3",
    capabilities=[
        Capability(
            tool="data.iceberg.read",
            action="read",
            resource="nyse:trades",
            descriptor_hash=descriptor_hash_for("data.iceberg.read"),
            cell_id=request.aqp_context.cell_id,
        ),
        # ... one per tool the agent may invoke during this run
    ],
    private_key_pem=settings.biscuit_signing_key_pem,
    ttl_seconds=900,
    cell_id=request.aqp_context.cell_id,
)

# 2. Attenuate per tool call — the agent narrows to exactly this call.
narrow = attenuate_for_call(
    parent_b64=issued.token_b64,
    tool="data.iceberg.read",
    action="read",
    resource="nyse:trades",
    descriptor_hash=descriptor_hash_for("data.iceberg.read"),
    cell_id=request.aqp_context.cell_id,
)
# Attach `narrow` as the X-Biscuit header on the MCP HTTP call.

# 3. Verify at MCP server — checks the attenuated chain.
verified = verify_biscuit(
    token_b64=request.headers["X-Biscuit"],
    public_key_pem=settings.biscuit_public_key_pem,
    expected_tool="data.iceberg.read",
    expected_action="read",
    expected_resource="nyse:trades",
    expected_descriptor_hash=descriptor_hash_for("data.iceberg.read"),
    expected_cell_id=request.aqp_context.cell_id,
)
```

## Capability shape

The `Capability` record carries four required fields:

| Field | Meaning |
| --- | --- |
| `tool` | MCP tool name, e.g. `data.iceberg.read`. |
| `action` | Verb, e.g. `read`, `write`, `delete`. |
| `resource` | Canonical resource id, e.g. `nyse:trades`. |
| `descriptor_hash` | SHA-256 of the canonical-JSON MCP tool descriptor (Phase 5 §8.4). |

Plus an optional `cell_id` that pins the capability to a specific
deployment cell (Phase 3 §6.2).

## Capability namespacing

The capability namespace matches the MCP tool name:

| Tool | Capability |
| --- | --- |
| `data.iceberg.read` | `read` |
| `data.iceberg.write` | `write` |
| `data.entities.search` | `read` |
| `data.entities.create` | `write` |
| `data.lineage.read` | `read` |
| `data.secrets.read` | NOT BISCUIT-GATED — uses BrokerCredentialStore (Rule 55) |

Adding a new tool with a new capability is purely additive — the
existing biscuits keep working for the tools they cover.

## Mint key rotation

The biscuit signing key is an ed25519 key pair. The private key
lives in Vault Transit (Phase 4 §7.6); the public key is projected
into every MCP server pod via a
[`VaultStaticSecret`](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp_platform/deployments/kubernetes/mesh-identity/vault-secrets-operator/sample-vault-static-secret.yaml)
named `biscuit-public-key`.

Rotation procedure (operator-level):

1. Generate a new ed25519 key pair via Vault Transit's
   `transit/keys/biscuit-signing/rotate`.
2. Vault Transit keeps the OLD key version live for 7 days.
3. Every MCP server now accepts biscuits signed by EITHER key
   for that 7-day overlap (the verify path tries the new key
   first, falls back to the old key on signature mismatch — TODO
   in Phase 5.5).
4. After 7 days, drop the old key version.

## Failure modes

| Failure | Behaviour |
| --- | --- |
| `biscuit-python` not installed (e.g. Windows dev) | `BiscuitUnavailable` raised; the agent runtime falls back to JWT-only delegation. The MCP server returns 503 if biscuit is required for the route. |
| Biscuit signature mismatch | `BiscuitVerificationError` raised; route returns 403 `biscuit_invalid`. |
| Biscuit capability doesn't match the route | `BiscuitVerificationError`; route returns 403 `biscuit_capability_mismatch`. |
| Biscuit expired | `BiscuitVerificationError`; route returns 401 `biscuit_expired`. |

## Why not just narrow the JWT?

JWTs are not attenuable. Once Auth0 mints a JWT with scopes
`[data:read, data:write]`, the agent CANNOT mint a derived JWT with
just `[data:read]` — that would require the agent to be its own AS
(it isn't) and would compromise the JWT signing key.

Biscuits sidestep this by encoding capabilities as facts the agent
can chain narrowing checks onto. The signature stays on the
authority block; chained blocks add restrictions, never expand them.

## Phase 5.5 follow-ups

1. **Agent runtime wire-up** — automate the
   `mint_biscuit + attenuate_for_call` calls on every MCP tool
   invocation in `aqp/agents/runtime.py`. Today the helpers are
   standalone.
2. **Key-rotation overlap window** — `verify_biscuit` accepts a list
   of public keys to try in order. Phase 5 ships the single-key
   verify; the multi-key fallback lands in Phase 5.5.
3. **MCP server-side enforcement** — wire `verify_biscuit` into the
   MCP HTTP request handler at `aqp/data/mcp/server.py` so every
   tool call that doesn't carry a valid biscuit gets 401.

## Related documents

- [RESTRUCTURING_PLAN.md §8.2](https://github.com/julianwiley/agentic_quant_platform/blob/main/RESTRUCTURING_PLAN.md)
- [aqp/auth/biscuit.py](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp/auth/biscuit.py)
- [aqp/auth/token_exchange.py](https://github.com/julianwiley/agentic_quant_platform/blob/main/aqp/auth/token_exchange.py) — the JWT broker biscuits run alongside.
- Biscuit specification: https://github.com/biscuit-auth/biscuit
- biscuit-python: https://github.com/biscuit-auth/biscuit-python
