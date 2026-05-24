# ADR 003 — Auth0 zero-trust two-layer security model

- **Status**: Accepted (2026-05-18)
- **Authors**: Platform team
- **Supersedes**: None
- **Related**: [ADR 005 — separated control plane](005-separated-control-plane.md), [aqp_docs/identity.md](../../identity.md), [aqp_docs/auth0-actions.md](../../auth0-actions.md)

## Context

AQP already uses Auth0 for the operator UI via the in-flight `aqp/auth/providers/auth0.py` plugin (AGENTS hard rule 27). What's missing for the refactor is the second layer: cryptographic JWT validation at every service boundary, resource-scoped claims so users only see their own resources, and a per-role scope matrix that the `aqp_control_plane` micro-project can enforce without ever importing `aqp.*`.

Three identity strategies were considered:

1. **Self-hosted Keycloak** — full control, but operations burden and one more stateful service per cluster.
2. **Single-layer Auth0 (current state)** — Auth0 only for the SPA login. Backend services still trust user-injected headers via session cookies.
3. **Two-layer Auth0 (recommended in prompt)** — Auth0 OIDC for the SPA + JWT (`RS256`) bearer tokens validated independently by every service via JWKS.

## Decision

Adopt the **two-layer Auth0 model** with the following invariants:

1. The Vite SPA in `aqp_client` performs Authorization Code + PKCE against the Auth0 tenant. Access tokens are short-lived (1 h) JWTs with `aud` = `https://api.aqp.internal/manage`.
2. Every backend service — `aqp` (FastAPI API), `aqp_control_plane` (micro-project), and the `rpi_kubernetes` `management/backend` shim — re-validates JWTs against the Auth0 JWKS independently using the shared validator in `aqp_platform_core/auth/`. **No service trusts a header set by another service.**
3. Auth0 Post-Login Action (template in `aqp_platform/terraform/modules/auth0_identity/post_login_action.js.tftpl`) calls `POST /_internal/auth0/sync` to fetch user-specific custom claims and injects them into the access token under the **`https://aqp.internal/`** namespace:
   - `https://aqp.internal/org_id` — tenancy boundary
   - `https://aqp.internal/roles` — coarse role list (`aqp-viewer`, `aqp-admin`, `aqp-operator`)
   - `https://aqp.internal/resources` — explicit resource ID allowlist (org-scoped)
   - `https://aqp.internal/workspace_id`, `https://aqp.internal/team_ids` — existing tenancy hints
4. M2M tokens for service-to-service calls (e.g. `aqp_client` → `aqp_control_plane`) mint through Auth0 Client Credentials. The proxy in `aqp/api/proxy.py` attaches a cached M2M token; `aqp_control_plane` validates it like any other JWT.
5. The four-role RBAC matrix from the refactor prompt becomes the canonical scope grid:

   | Role             | Scopes granted                                                                                      |
   | ---------------- | ---------------------------------------------------------------------------------------------------- |
   | `aqp-viewer`     | `read:infrastructure`                                                                                |
   | `aqp-operator`   | `read:infrastructure` + `manage:agents`                                                              |
   | `aqp-admin`      | `read:infrastructure` + `manage:agents` + `manage:infrastructure`                                    |
   | `aqp-superadmin` | All of the above + `admin:cluster` (only role that bypasses `filter_resources`)                      |

6. Every list endpoint in both `aqp` and `aqp_control_plane` passes its result list through `aqp_platform_core.auth.resource_filter.filter_resources(items, jwt_payload)` before returning. The filter respects `admin:cluster` (returns everything) and otherwise intersects against the `resources` claim.

## Consequences

**Positive**
- Zero-trust between services. A compromised `aqp_client` container can issue requests but cannot forge claims — the control plane re-validates.
- Resource scoping moves from "frontend hides things" to "backend cannot return things". Defence in depth.
- Auth0 is already in production for the SPA; the only delta is adding M2M tokens and the `resources` claim.
- The `aqp_control_plane` micro-project gets a clean security boundary without importing `aqp.auth.*` — it depends on `aqp_platform_core/auth/` only.

**Negative**
- Every API request pays JWKS verification cost (~0.2 ms with `lru_cache`). Acceptable.
- The `https://aqp/` → `https://aqp.internal/` namespace rename requires one release of dual-reading both namespaces (handled by `auth_claims_namespace_aliases` setting).
- Operators need to be onboarded to one of the four roles before they can use the new control plane — solved by `/build/scripts/provision_auth0.py` running on bootstrap.

## Alternatives considered

- **Self-hosted Keycloak** — rejected. Adds operational burden without business value. Auth0 plays well with Terraform (already in `aqp_platform/terraform/modules/auth0_identity/`).
- **Cookie-only sessions** — rejected. Backend services would have to trust whatever set the cookie; doesn't compose with the cross-service M2M case.
- **Opaque tokens with introspection** — rejected. Adds a round trip per request against Auth0's `/oauth/token/introspect`, and Auth0's free tier rate-limits it.

## Implementation references

- JWT validator: `aqp_platform_core/auth/validator.py` (extracted from `aqp/auth/providers/auth0.py`)
- Resource filter: `aqp_platform_core/auth/resource_filter.py`
- Claims namespace setting: `aqp/config/settings.py::auth_claims_namespace`, `auth_claims_namespace_aliases`
- Auth0 Action template: `aqp_platform/terraform/modules/auth0_identity/post_login_action.js.tftpl`
- Sync endpoint: `aqp/api/routes/auth0_sync.py`
- Terraform Auth0 module: `aqp_platform/terraform/modules/auth0_identity/main.tf`
- Provisioning script: `aqp_platform/build/scripts/provision_auth0.py`
