# aqp-index debt — Phase 4 mesh + identity

> Per the always-on
> [aqp-index-reflect rule](../rules/aqp-index-reflect.mdc), Phase 4
> §7 of
> [RESTRUCTURING_PLAN.md](../../RESTRUCTURING_PLAN.md) touches enough
> qualifying surfaces (new Cedar policy engine integration, two NEW
> IdentityProvider classes, a NEW SecretStore class, four new
> per-cell K8s component trees, two new docs files) that
> `aqp_index/` MUST be refreshed by the
> [`aqp-index-curator`](../agents/aqp-index-curator.md) subagent in
> the same PR — OR a debt note (this file) must capture the changed
> surfaces so the curator's next scheduled pass picks them up.
>
> This note is option 2. Invoke the curator before merging if at all
> possible.

## Surfaces changed in Phase 4

### `aqp/`

- **`aqp/api/security_cedar.py`** (NEW) — `require_cedar` FastAPI
  dependency + `CedarRequest` / `CedarDecision` / `CedarPolicySet`
  dataclasses + `evaluate(...)` engine + `load_policies(force=False)`
  loader + `reset_cedar_cache()` test helper + audit hooks
  (`_audit_decision`) that stamp `aqp.cedar.*` OTEL attributes.
- **`aqp/auth/providers/spiffe.py`** (NEW) — `SpiffeIdentityProvider`
  implementing the `IdentityProvider` ABC. Only `m2m_token()` is
  functional; user-flow methods raise `IdentityProviderError`.
  Reads SVIDs from the SPIRE Workload API socket.
- **`aqp/auth/providers/pomerium.py`** (NEW) — `PomeriumAccessProvider`
  + `extract_pomerium_claims(request)` helper. Mirrors the
  existing `CloudflareAccessProvider` pattern. Validates
  `X-Pomerium-Jwt-Assertion` against Pomerium's JWKS.
- **`aqp/credentials/stores/vault_static_secret_store.py`** (NEW) —
  `VaultStaticSecretStore` SecretStore at priority 15 (above
  AppRole Vault 20, below M2M 10). Reads VSO-projected secrets
  from `/var/run/secrets/vault-secrets-operator/<service>.<purpose>/`.
- **`pyproject.toml`** — added `cedarpy>=4.0.0` to the `[auth]`
  extra.

### `aqp_platform/configs/cedar/policies/` (NEW)

- `00_cells.cedar` — cells-router action policies (Phase 3 §6.2).
- `01_manage.cedar` — `/manage/*` mutations (secrets, builds,
  terraform, tenants).
- `02_agents.cedar` — agent-sandbox MCP tool authz (Phase 5 §8.1).
- `03_data.cedar` — DataMCP tool surface dataset gates.
- `README.md` — entity model, action vocabulary, sensitivity tiers.

### `aqp_platform/deployments/kubernetes/mesh-identity/` (NEW TREE)

- `README.md` — overall component layout + apply order.
- `spire/` — namespace + Server StatefulSet + Agent DaemonSet.
- `linkerd/` — namespace + Helm-based control plane install
  (linkerd-crds, linkerd-control-plane, linkerd-viz HelmReleases).
- `pomerium/` — namespace + Helm install + `route-manage.yaml`
  gateway HTTPRoute for `/manage/*`.
- `vault-secrets-operator/` — namespace + operator HelmRelease +
  sample `VaultStaticSecret` for cell Postgres credentials.

### `aqp_platform/deployments/kubernetes/cells/` (UPDATED)

- `shared-std-us-east-1a/namespace.yaml` — added
  `linkerd.io/inject: enabled` annotation.
- `shared-prem-us-east-1a/namespace.yaml` — same.
- `silo-reg-acme/namespace.yaml` — same.

### `aqp_platform/build/docker/aqp-edge/`

- `envoy.template.yaml` — added `aqp_pomerium_proxy` cluster +
  `/manage/*` prefix route that forwards to Pomerium BEFORE the
  cell-router decision (Phase 4 §7.5).

### `aqp_docs/`

- `aqp_docs/docs/concepts/identity/spiffe-workload-identity.md`
  (NEW) — concept doc covering trust domain layout, deployment
  shape, AQP integration via `SpiffeIdentityProvider`, pod template
  requirements, rotation/revocation, failure modes.
- `aqp_docs/docs/how-to/linkerd-spire-rollout.md` (NEW) —
  operator-facing runbook covering apply order, mTLS validation,
  Pomerium IAP validation, Cedar gate validation, VSO rotation
  validation, rollback steps.

## Files the curator should refresh

| `aqp_index/` file | Why it needs a refresh |
| --- | --- |
| `aqp_index/projects/aqp.md` | New `aqp/api/security_cedar.py` module; two new identity provider modules under `aqp/auth/providers/`; new credential store. |
| `aqp_index/projects/aqp_platform.md` | New `mesh-identity/` K8s tree + new `cedar/policies/` config tree + envoy template changes. |
| `aqp_index/projects/aqp_docs.md` | Two new docs pages (concepts + how-to). |
| `aqp_index/sources-of-truth.md` | Cedar policy bundle is the new SSoT for application-layer authz decisions; SPIFFE Workload API is the new M2M source-of-truth; VSO-projected Secrets are the new at-rest secret SSoT. |
| `aqp_index/config-sets/identity-providers.md` | Three providers now: Auth0 / Entra (user-flow), SPIFFE (workload), Pomerium (edge). |
| `aqp_index/config-sets/secret-stores.md` | Five concrete stores now (env / file / cloud / AppRole-Vault / VSO-Vault). Priority chain: M2M (10) > VSO (15) > Vault AppRole (20) > Cloud SM (30) > File (50) > Env (100). |

## Phase 4 §7 sub-section coverage

| RESTRUCTURING_PLAN.md sub-§ | Status |
| --- | --- |
| §7.1 Linkerd 2.16 | Helm-based per-cell install manifests + namespace inject annotations + golden-signal extension scaffold |
| §7.2 SPIRE 1.10 + SPIFFE | StatefulSet + DaemonSet + RBAC + ConfigMap + `SpiffeIdentityProvider` Python class + concept doc |
| §7.3 Cedar policy engine | `cedarpy` in `[auth]` extra + `aqp/api/security_cedar.py` + 4 policy files + README. Validated end-to-end with `cedarpy.is_authorized` (Allow / Deny / forbid override) |
| §7.4 OPA confined to admission | Already true via Kyverno (Phase 2 §5.3). Documented in Cedar README. |
| §7.5 Pomerium IAP | Helm install + per-route HTTPRoute + `PomeriumAccessProvider` Python class + envoy.template wiring |
| §7.6 vault-secrets-operator | Operator install + sample `VaultConnection` / `VaultAuth` / `VaultStaticSecret` + `VaultStaticSecretStore` Python class + 10 pytest unit tests (all pass in isolation) |

## Follow-ups (Phase 4.5)

1. **M2MTokenIssuer dispatch** — wire `AQP_AUTH_M2M_PROVIDER=spiffe`
   into the issuer so SPIFFE replaces Auth0 for M2M without
   touching user OIDC flows. Phase 4 ships the provider class but
   not the routing change.
2. **Per-cell `ClusterSPIFFEID` CRDs** binding workload selectors
   to specific SPIFFE IDs (today the spine relies on the default
   k8s_psat attestor).
3. **`mesh-identity` ApplicationSet column** — extend
   `applicationsets/cells-appset.yaml` so each cell stamps one
   Application per `mesh-identity/<component>` directory.
4. **Linkerd trust anchor from SPIRE** — wire SPIRE-issued
   trust anchor into Linkerd's Identity service so the mesh uses
   SPIFFE IDs natively (today they're independent CAs).
5. **Pomerium with Entra ID** — Phase 4 wires Auth0 only; Entra
   ID dual-IdP support lands in Phase 4.5 to match the
   `aqp_ui` dual-identity contract.
6. **Cedar policy hot-reload** — add `POST /manage/cedar/reload`
   endpoint protected by `admin:cluster` so operators can refresh
   the policy bundle without a process restart.
7. **Pre-existing import cycle** — the test suite for
   `tests/credentials/test_*.py` fails to collect due to a
   circular import that existed before Phase 4. The
   `VaultStaticSecretStore` smoke tests pass in isolation; fold
   the test wire-up into the broader import-cycle remediation
   when that lands.
8. **CI image build for Pomerium / vault-secrets-operator** — neither
   ships an AQP-owned image; the Phase 4.5 follow-up adds a
   sidecar / init-container if needed.

## Provenance

- Discovered while implementing
  [RESTRUCTURING_PLAN.md](../../RESTRUCTURING_PLAN.md) Phase 4 in
  the same PR.
- All surfaces enumerated above show up in `git status` for this
  PR; the curator can scan that diff directly.
