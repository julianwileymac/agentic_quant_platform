# aqp_index debt — Data Layer Selective Additive Enhancement

Per the always-on
[`aqp-index-reflect.mdc`](../../.cursor/rules/aqp-index-reflect.mdc)
rule: this PR touches qualifying surfaces and must either invoke the
[`aqp-index-curator`](../../.cursor/agents/aqp-index-curator.md)
subagent or open a debt note. The implementation was driven by an
explicit per-workstream plan with strict time pressure; this debt
note records the deferred curator pass so a follow-up commit can
refresh `aqp_index/` accurately and in one shot.

## Surfaces touched (qualifying for reflection)

### Repo-root governance docs

- [AGENTS.md](../../AGENTS.md) — appended hard rules 48, 49, 50, 51
  to the existing 47-rule list. The four new rules cover bipartite
  lineage, MCP RFC 9728/8707 conformance, per-user OAuth vault,
  and TenancyStrategy.

### `.cursor/rules/` (new files; no edits to existing rules)

- `.cursor/rules/lineage-graph.mdc` (workstream A + B + C scope)
- `.cursor/rules/mcp-rfc-conformance.mdc` (workstream E scope)
- `.cursor/rules/external-oauth.mdc` (workstream D scope)
- `.cursor/rules/tenancy-strategy.mdc` (workstream F scope)

### `configs/`

- No changes. (External configs land in
  `aqp_platform/configs/deployment/topology.yaml` — recorded below.)

### `aqp_platform/`

- `aqp_platform/configs/deployment/topology.yaml` — added the
  `marquez` service entry for the OpenLineage relay (workstream B).
  Pairs with the new `URL_FALLBACK_FIELDS` entry in
  [`aqp/config/topology_fallback.py`](../../aqp/config/topology_fallback.py).

### Public surface of `aqp_*` packages

| Package | New public symbols |
| --- | --- |
| `aqp.lineage.graph` | `LineageGraphWriter`, `BipartiteGraphObserver`, `iceberg_snapshot_address`, `fallback_content_hash`, `register_bipartite_observer` |
| `aqp.lineage.openlineage` | `OpenLineageOutboxObserver`, `aqp_event_to_openlineage`, `drain_outbox_once`, `post_openlineage_event`, `register_openlineage_observer` |
| `aqp.auth.signing` | `ActorIdentity`, `Ed25519Signer`, `NullSigner`, `sign_transform_payload`, `verify_signature`, `canonical_transform_payload`, `get_signer_for` |
| `aqp.auth.signing_keys` | `issue_signing_key`, `archive_public_key`, `get_public_key_for`, `generate_ed25519_keypair` |
| `aqp.auth.external_oauth` | `ExternalOAuthProvider`, `ExternalOAuthProviderMeta`, `ExternalProviderConfig`, `ExternalTokenResponse`, `list_external_oauth_providers`, `get_external_oauth_provider` |
| `aqp.auth.external_oauth.flow` | `start_authorize_flow`, `complete_authorize_flow` |
| `aqp.auth.external_oauth.providers` | `GenericExternalOAuthProvider`, `GitHubExternalOAuthProvider`, `FredExternalOAuthProvider`, `BloombergExternalOAuthProvider`, `RefinitivExternalOAuthProvider` |
| `aqp.tenancy` | `TenancyStrategy`, `TenancyStrategyMeta`, `TenancyStrategyFactory`, `SharedSchemaRLSStrategy`, `SchemaPerTenantStrategy`, `DatabasePerEnterpriseStrategy`, `HybridStrategy`, `get_tenancy_factory`, `list_tenancy_strategy_classes` |
| `aqp.tenancy.runtime_context` | `set_runtime_context`, `reset_runtime_context`, `get_runtime_context` |
| `aqp.tenancy.rls_policies` | `RLS_TABLES`, `RlsTable`, `enable_rls_ddl`, `disable_rls_ddl`, `policy_ddl` |
| `aqp.credentials.stores.user_oauth_token_store` | `UserOAuthTokenStore`, `install_user_oauth_store`, `PRIORITY_USER_OAUTH` |
| `aqp.credentials.vault_transit` | `encrypt`, `decrypt`, `deterministic_vault_path` |
| `aqp.api.well_known` | `build_well_known_router` |
| `aqp.api.mcp_audience` | `validate_mcp_audience`, `build_resource_metadata_header`, `get_mcp_audience_mode`, `get_data_mcp_canonical_uri`, `get_codebase_mcp_canonical_uri` |
| `aqp.api.middleware.tenancy_middleware` | `TenancyContextMiddleware` |
| `aqp.api.routes.oauth_connections` | `router` (`/me/oauth-connections/*`) |
| `aqp.data.mcp.tools.lineage_graph` | `LineageAncestryTool`, `LineageImpactTool` (DataMCP tools `data.lineage.ancestry`, `data.lineage.impact`) |
| `aqp.data.mcp.tools.oauth_connections` | `ListOAuthConnectionsTool` (DataMCP tool `data.oauth.list_connections`) |
| `aqp.persistence.models_lineage_graph` | `DatasetVertex`, `TransformVertex`, `LineageEdge` |
| `aqp.persistence.models_openlineage` | `OpenLineageOutbox` |
| `aqp.persistence.models_signing_keys` | `SigningKeyArchive` |
| `aqp.persistence.models_oauth_tokens` | `UserOAuthToken` |
| `aqp.tasks.openlineage_relay_tasks` | `drain_openlineage_outbox` (Celery beat) |
| `aqp.tasks.token_refresh_tasks` | `refresh_external_oauth_tokens` (Celery beat) |

### Alembic migrations (additive only)

- `0059_lineage_graph_v2.py`
- `0060_openlineage_outbox.py`
- `0061_lineage_signing_archive.py`
- `0062_user_oauth_tokens.py`
- `0063_tenancy_strategy.py`
- `0064_schema_per_tenant_bootstrap.py`

### Settings (`AQP_*` env knobs)

- `AQP_MCP_DATA_CANONICAL_URI`, `AQP_MCP_CODEBASE_CANONICAL_URI`,
  `AQP_MCP_REQUIRE_RFC8707`, `AQP_BACKEND_EXTERNAL_URL` (workstream E)
- `AQP_LINEAGE_SIGNING_ENABLED`, `AQP_LINEAGE_SIGNING_MODE`
  (workstream C)
- `AQP_LINEAGE_GRAPH_ENABLED` (workstream A)
- `AQP_LINEAGE_OPENLINEAGE_RELAY_ENABLED`,
  `AQP_LINEAGE_OPENLINEAGE_MARQUEZ_URL`,
  `AQP_LINEAGE_OPENLINEAGE_NAMESPACE`,
  `AQP_LINEAGE_OPENLINEAGE_RELAY_BATCH` (workstream B)
- `AQP_TENANCY_DEFAULT_STRATEGY`, `AQP_TENANCY_RLS_ENFORCE`,
  `AQP_TENANCY_DB_PER_ENTERPRISE_POOL_TTL_SECONDS` (workstream F)
- `AQP_USER_OAUTH_ENABLED`, `AQP_USER_OAUTH_REFRESH_WINDOW_SECONDS`,
  `AQP_USER_OAUTH_LOCAL_KEY` (workstream D)

## Files the curator should refresh

When the curator runs Plan → Scan → Diff → Refresh → Validate, the
following `aqp_index/` files are expected to require updates:

- `aqp_index/architecture/lineage.md` — add the bipartite graph
  layer + OpenLineage relay shape.
- `aqp_index/architecture/credentials.md` — add the new
  `UserOAuthTokenStore` priority slot + Vault Transit envelope flow.
- `aqp_index/architecture/tenancy.md` (net-new) — TenancyStrategy
  ABC + four concrete strategies.
- `aqp_index/architecture/mcp.md` — RFC 9728 + RFC 8707 conformance.
- `aqp_index/code/aqp-lineage.md` (net-new) — public symbols + entry
  points for `aqp/lineage/` package.
- `aqp_index/code/aqp-tenancy.md` (net-new) — public symbols + entry
  points for `aqp/tenancy/` package.
- `aqp_index/code/aqp-auth.md` — append the new
  `aqp.auth.signing*` + `aqp.auth.external_oauth.*` surface.
- `aqp_index/code/aqp-credentials.md` — append
  `vault_transit` + `user_oauth_token_store` entries.
- `aqp_index/skills/aqp-rules-reviewer-skill.md` — incorporate the
  new hard rules 48–51 in the rubric.
- `aqp_index/subagents/registry.md` — verify the existing
  `aqp-hard-rules-reviewer` registry mirrors the new hard rules.

## Pointer for the curator pass

When invoking the curator subagent later:

```
@aqp-index-curator refresh aqp_index/ for the Data Layer Selective
Additive Enhancement (workstreams A, B, C, D, E, F). Use this debt
note as the input scan and produce a single PR that closes the debt.
```

## Status

- [ ] Curator pass scheduled
- [ ] Curator pass complete
- [ ] Debt closed (remove this file)
