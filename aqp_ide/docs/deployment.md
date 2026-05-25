# AQP IDE deployment

Three deployment paths in increasing order of operational ambition:

1. **Local** — `aqp-cli ide start`. Single user, single tenant. Default for
   inner-loop development.
2. **Single-pod Kubernetes** — kustomize at
   [`../../aqp_platform/deployments/kubernetes/aqp-ide/`](../../aqp_platform/deployments/kubernetes/aqp-ide/).
   One Theia pod per cluster, fronted by an Ingress at
   `ide.aqp.fund`. Suitable for a small team sharing one tenancy.
3. **Theia Cloud (multi-tenant)** — Phase B. Per-user pods + PVCs
   managed by the Theia Cloud operator. Manifests scaffolded under
   `aqp-ide/theia-cloud/` with a `DEFERRED.md` marker; not deployed in
   this release.

## Local (`aqp-cli ide`)

See [cli-entrypoint.md](cli-entrypoint.md) for the full reference. The
short version:

```bash
aqp-cli auth login --device
aqp-cli ide install
aqp-cli ide build --dev
aqp-cli ide start --open
```

## Single-pod Kubernetes

Path: [`../../aqp_platform/deployments/kubernetes/aqp-ide/`](../../aqp_platform/deployments/kubernetes/aqp-ide/)

| File | Purpose |
| --- | --- |
| `kustomization.yaml` | Bundles every manifest below |
| `namespace.yaml` | Creates `aqp-ide` namespace with tenant label |
| `deployment.yaml` | Single Theia pod; PVC mount for `/home/project` |
| `service.yaml` | ClusterIP `:3000` |
| `ingress.yaml` | cert-manager + Let's Encrypt for `ide.aqp.fund` |
| `configmap-aqp.yaml` | `AQP_THEIA_*` env (non-secret) |
| `secret-template.yaml` | Commented-out template for sealed secrets |
| `networkpolicy.yaml` | Default-deny + explicit allow to `/aqp/*` + `/mcp/*` + Auth0 |
| `README.md` | Operator runbook for this overlay |

Apply with:

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/aqp-ide/
```

### Image build

The Docker image is built from [`../browser.Dockerfile`](../browser.Dockerfile):

```bash
docker build -t aqp/aqp-ide:latest -f aqp_ide/browser.Dockerfile aqp_ide/
docker push aqp/aqp-ide:latest
```

Update the `image` field in `deployment.yaml` to the pinned tag.

### Cloudflare tunnel

For a public-facing `ide.aqp.fund`, see the AQP Cloudflare tunnel
documentation in `aqp_docs/docs/concepts/identity/management-engine.md` and the matching
Terraform stack in `aqp_platform/terraform/cloudflare/`. The Cloudflare
tunnel + DNS entries live in AQP — `rpi_kubernetes` owns ONLY the
portal's `julianwiley.com` tunnel (per the always-on
`rpi-k8s-governance.mdc` rule).

### Secrets

The `configmap-aqp.yaml` carries the non-secret runtime config (Auth0
client_id is public per PKCE, the AQP API base URL is non-sensitive,
the MCP URLs + audiences are non-secret URLs). True secrets (none in
this release — the Theia backend doesn't hold any) would go via the
existing AQP `CredentialResolver` chain (rule 26) — usually
SealedSecrets + Vault Transit envelope encryption per AQP's standard
pattern.

## Theia Cloud (Phase B)

Path: [`../../aqp_platform/deployments/kubernetes/aqp-ide/theia-cloud/`](../../aqp_platform/deployments/kubernetes/aqp-ide/theia-cloud/)

Status: **scaffolded but NOT deployed**. The `DEFERRED.md` marker
explains the trigger (≥2 internal users need isolated workspaces).

The Theia Cloud operator (open-source, EPL-2.0, Java-based) reconciles
three custom resources:

- `AppDefinition.theia.cloud/v1beta10` — the AppDefinition that
  describes the Theia browser image + per-tenant resource limits.
- `Workspace.theia.cloud/v1beta5` — per-user persistent workspaces.
- `Session.theia.cloud/v1beta8` — per-session pods (the actual Theia
  instances).

The scaffolded files:

| File | Purpose |
| --- | --- |
| `app-definition.yaml` | `AppDefinition` CRD for the AQP IDE image |
| `values.example.yaml` | Helm values for the `theia-cloud` chart |
| `README.md` | Theia Cloud operator install + tenant onboarding |
| `DEFERRED.md` | Trigger criteria + Phase B contract |

When ready to ship, install the three official Theia Cloud Helm charts
(`theia-cloud-base`, `theia-cloud-crds`, `theia-cloud`) per
https://theia-cloud.io/documentation/ and apply the `AppDefinition` from
this directory.

## Domain isolation

| Domain | Owned by | Tunnel | IdP |
| --- | --- | --- | --- |
| `ide.aqp.fund` | AQP (this repo) | AQP Cloudflare tunnel | Auth0 `aqp-fund.us.auth0.com` |
| `api.aqp.fund`, `manage.aqp.fund` | AQP | AQP Cloudflare tunnel | Auth0 |
| `julianwiley.com` | `rpi_kubernetes` | Portal-only Cloudflare tunnel | Microsoft Entra |

The two domains share no certs, no IdP, no tunnels. The `web` namespace
NetworkPolicy in `rpi_kubernetes` continues to deny egress to every
`aqp-*` namespace.

## See also

- [cli-entrypoint.md](cli-entrypoint.md) — `aqp-cli ide` reference
- `aqp_docs/docs/concepts/identity/management-engine.md` — AQP cluster + cloudflare ops
- `aqp_docs/docs/architecture/decisions/004-provider-abstraction.md`
- `aqp_docs/docs/architecture/decisions/005-separated-control-plane.md`
- Theia Cloud upstream: https://theia-cloud.io/
