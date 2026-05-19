# Auth0 checklist for Kubernetes login

This checklist captures the Auth0-side changes required for the Kubernetes
deployment to support login through the Vite SPA and JWT validation in
`aqp-core` / `aqp_control_plane`.

Current local `.env` discovery:

- Auth0 tenant domain: `dev-4zy4dzau.us.auth0.com`
- SPA client id: present in `.env`
- SPA / confidential client secret: present in `.env`
- M2M client id/secret: **missing**; create a dedicated M2M app before enabling
  the Auth0 Action in production.
- SCIM bearer token hash: **missing**; SCIM remains disabled until created.

Do not paste secrets into this document. Store secrets in `.env` locally and in
your production secret manager / sealed-secret pipeline for Kubernetes.

## 1. API Resource Server

Auth0 Dashboard path: **Applications → APIs → Create API**.

Create or update:

| Field | Value |
| --- | --- |
| Name | `AQP Management API` |
| Identifier | `https://api.aqp.internal/manage` |
| Signing Algorithm | `RS256` |
| RBAC | enabled |
| Add Permissions in Access Token | enabled |

Required permissions:

| Permission | Purpose |
| --- | --- |
| `read:infrastructure` | View deployment status, pod health, logs, non-secret config |
| `manage:agents` | Start/stop/restart/scale assigned agents and bot workloads |
| `manage:infrastructure` | Deploy/update services and non-secret config within assigned org |
| `admin:cluster` | Full cluster control and resource-filter bypass |
| `scim:write` | Auth0 SCIM provisioning into `/scim/v2/*` |

Migration permissions to retain until all older AQP routes are moved to the new
control-plane scope grid:

| Permission | Why keep temporarily |
| --- | --- |
| `data:read` | Existing AQP data/read routes still check it |
| `data:write` | Existing AQP mutation routes still check it |
| `deploy:run` | Existing Terraform control-plane routes still check it |
| `deploy:halt` | Existing Terraform halt/kill-switch integrations still check it |

Terraform source of truth:

- [`terraform/modules/auth0_identity/main.tf`](../../terraform/modules/auth0_identity/main.tf)
- [`terraform/modules/auth0_identity/variables.tf`](../../terraform/modules/auth0_identity/variables.tf)

## 2. SPA Application (`aqp-client`)

Auth0 Dashboard path: **Applications → Applications → Create Application → Single Page Application**.

Use the `.env` client id already present for this app if it is the AQP SPA.

Configure:

| Setting | Values |
| --- | --- |
| Application Type | Single Page Application |
| Token Endpoint Authentication Method | `None` |
| Grant Types | Authorization Code, Refresh Token |
| Allowed Callback URLs | `http://127.0.0.1:3001/auth/callback`, `http://localhost:3001/auth/callback`, `https://api.aqp.enterprise.com/auth/callback` |
| Allowed Logout URLs | `http://127.0.0.1:3001`, `http://localhost:3001`, `https://api.aqp.enterprise.com` |
| Allowed Web Origins | `http://127.0.0.1:3001`, `http://localhost:3001`, `https://api.aqp.enterprise.com` |
| Allowed Origins (CORS) | same as Web Origins |

Kubernetes ConfigMap values now generated from `.env`:

```yaml
VITE_AUTH_REQUIRED: "true"
VITE_AUTH0_DOMAIN: "dev-4zy4dzau.us.auth0.com"
VITE_AUTH0_CLIENT_ID: "<from .env AUTH0_CLIENT_ID>"
VITE_AUTH0_AUDIENCE: "https://api.aqp.internal/manage"
```

## 3. Machine-to-Machine Application (`aqp-m2m`)

Auth0 Dashboard path: **Applications → Applications → Create Application → Machine to Machine**.

Create a dedicated app; do **not** reuse the SPA client secret for M2M.

Grant it access to the API Resource Server:

| API | Scopes |
| --- | --- |
| `https://api.aqp.internal/manage` | `read:infrastructure`, `manage:infrastructure`, `data:read`, `scim:write`, `deploy:run`, `deploy:halt` |

Store:

| AQP variable | Source |
| --- | --- |
| `AQP_AUTH_M2M_CLIENT_ID` | M2M Application Client ID |
| `AQP_AUTH_M2M_CLIENT_SECRET` | M2M Application Client Secret |
| `AQP_AUTH_M2M_AUDIENCE` | `https://api.aqp.internal/manage` |

The current `.env` does not yet contain the M2M client id/secret, so the
generated Kubernetes Secret intentionally leaves `AQP_AUTH_M2M_CLIENT_SECRET`
empty/placeholder until you create the app.

## 4. Post-Login Action

The Action template lives at:

[`terraform/modules/auth0_identity/post_login_action.js.tftpl`](../../terraform/modules/auth0_identity/post_login_action.js.tftpl)

Configure the deployed Action with:

| Placeholder | Value |
| --- | --- |
| `claims_namespace` | `https://aqp.internal/` |
| `api_audience` | `https://api.aqp.internal/manage` |
| `sync_url` | production: `https://api.aqp.enterprise.com/_internal/auth0/sync` |

The Action injects these custom claims:

| Claim | Example |
| --- | --- |
| `https://aqp.internal/org_id` | `org_abc123` |
| `https://aqp.internal/workspace_id` | `workspace_abc123` |
| `https://aqp.internal/roles` | `["aqp-operator"]` |
| `https://aqp.internal/resources` | `["aqp-api", "aqp-worker"]` |
| `https://aqp.internal/scopes` | `["read:infrastructure", "manage:agents"]` |

The backend still reads the legacy `https://aqp/` namespace for one release,
but new tokens should use `https://aqp.internal/`.

## 5. Roles and assignments

Create roles:

| Role | Permissions |
| --- | --- |
| `aqp-viewer` | `read:infrastructure`, `data:read` |
| `aqp-operator` | `read:infrastructure`, `manage:agents`, `data:read` |
| `aqp-admin` | `read:infrastructure`, `manage:agents`, `manage:infrastructure`, `data:read`, `data:write`, `deploy:run`, `deploy:halt` |
| `aqp-superadmin` | all above plus `admin:cluster`, `scim:write` |

Assign your test user to `aqp-superadmin` first to verify end-to-end login.
Then move down to `aqp-operator` or `aqp-viewer` to verify resource filtering.

## 6. Kubernetes apply order

The safe apply order is:

```powershell
# 1. Apply tracked, non-secret manifests and placeholder Secret templates.
kubectl apply -k deployments/kubernetes/overlays/dev

# 2. Apply locally generated real Secret manifests (git-ignored).
kubectl apply -f deployments/kubernetes/generated/aqp-secrets.local.yaml
kubectl apply -f deployments/kubernetes/generated/aqp-admin-secrets.local.yaml

# 3. Restart workloads so env vars are re-read.
kubectl -n aqp rollout restart deployment/aqp-core deployment/aqp-client deployment/aqp-worker
kubectl -n aqp-admin rollout restart deployment/aqp-cp
```

Do not run this until `kubectl get ns` succeeds against the intended context.

## 7. Verification

```powershell
kubectl -n aqp get configmap aqp-config -o yaml
kubectl -n aqp-admin get configmap aqp-config -o yaml
kubectl -n aqp get secret aqp-secrets -o jsonpath='{.data.AQP_AUTH_OIDC_CLIENT_SECRET}'
kubectl -n aqp-admin get secret aqp-secrets -o jsonpath='{.data.AQP_AUTH_OIDC_CLIENT_SECRET}'
```

Frontend login should no longer show:

> Authentication is required ... frontend was not given identity-provider configuration

Instead, it should redirect to Auth0 Universal Login for the
`dev-4zy4dzau.us.auth0.com` tenant.
