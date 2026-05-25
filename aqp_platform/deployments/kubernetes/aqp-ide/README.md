# aqp-ide Kubernetes overlay

Single-pod K8s deployment for the AQP IDE (Theia 1.72 + six AQP
extensions). Fronted by an Ingress at `ide.aqp.fund` with cert-manager
+ Let's Encrypt.

## Files

| File | Purpose |
| --- | --- |
| [kustomization.yaml](kustomization.yaml) | Bundles every manifest below |
| [namespace.yaml](namespace.yaml) | `aqp-ide` namespace with Pod Security Admission `baseline` |
| [configmap-aqp.yaml](configmap-aqp.yaml) | `AQP_THEIA_*` non-secret config |
| [secret-template.yaml](secret-template.yaml) | Template for ExternalSecret -> Vault |
| [deployment.yaml](deployment.yaml) | Single Theia pod + 20 Gi PVC for `/home/project` |
| [service.yaml](service.yaml) | ClusterIP `:3000` |
| [ingress.yaml](ingress.yaml) | nginx + cert-manager Let's Encrypt for `ide.aqp.fund` |
| [networkpolicy.yaml](networkpolicy.yaml) | Default-deny + explicit allows |
| [theia-cloud/](theia-cloud/) | Phase B scaffolding (NOT deployed in this release) |

## Apply

```bash
# From the monorepo root:
kubectl apply -k aqp_platform/deployments/kubernetes/aqp-ide/

# Watch it come up:
kubectl -n aqp-ide get pods -w
kubectl -n aqp-ide logs deploy/aqp-ide
```

## Image build

The Docker image is built from `aqp_ide/browser.Dockerfile`:

```bash
docker build -t aqp/aqp-ide:latest -f aqp_ide/browser.Dockerfile aqp_ide/
docker push aqp/aqp-ide:latest
```

For multi-arch builds (rule 4 of `.cursor/rules/aqp-platform.mdc`),
use buildx:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t aqp/aqp-ide:latest \
  -f aqp_ide/browser.Dockerfile \
  --push \
  aqp_ide/
```

## Auth0 secret wiring

The Auth0 SPA `client_id` (public per PKCE but rotate-able per
environment) is projected via External Secrets Operator from Vault.
Replace the commented stub in [secret-template.yaml](secret-template.yaml)
with a real `ExternalSecret` of kind `aqp-ide-auth0` and uncomment the
`envFrom.secretRef` in [deployment.yaml](deployment.yaml).

## Cloudflare tunnel + DNS

The public DNS + tunnel for `ide.aqp.fund` is managed by AQP's
Cloudflare Terraform stack at `aqp_platform/terraform/cloudflare/`. The
matching `cloudflared` deployment lives in the `aqp-edge` namespace,
shared across `aqp.fund`, `api.aqp.fund`, `manage.aqp.fund`, and
`ide.aqp.fund`.

Domain isolation: this is AQP's namespace. The portal's
`julianwiley.com` tunnel lives in the `rpi_kubernetes` repo and shares
nothing with this stack (different certs, different IdP, different
tunnel) — per the always-on `rpi-k8s-governance.mdc` rule.

## Validation

```bash
# Kustomize build + dry-run apply:
kubectl kustomize aqp_platform/deployments/kubernetes/aqp-ide/ \
  | kubectl apply --dry-run=client -f -

# Check the Ingress controller picked up the route:
kubectl -n aqp-ide get ingress aqp-ide -o yaml

# Reach the running IDE from a port-forward (for cluster-internal
# testing without DNS):
kubectl -n aqp-ide port-forward svc/aqp-ide 3000:3000
# Then open http://localhost:3000
```

## See also

- [../../../aqp_ide/docs/deployment.md](../../../aqp_ide/docs/deployment.md)
- [theia-cloud/README.md](theia-cloud/README.md) (Phase B)
- `aqp_docs/docs/concepts/identity/management-engine.md`
