# aqp-ui Kubernetes manifests

Base Kustomize bundle for the cloud-hosted, customer-facing
`aqp_ui` Next.js application.

## Layout

```
aqp_platform/deployments/kubernetes/base/aqp-ui/
+- kustomization.yaml      # Lists every resource below
+- namespace.yaml          # ns: aqp-ui, with FinOps labels
+- serviceaccount.yaml     # ESO + Vault kubernetes-auth binding
+- deployment.yaml         # Next.js standalone, port 3000, 3 replicas
+- service.yaml            # ClusterIP :80 -> :http (3000)
+- hpa.yaml                # 3-20 replicas, CPU 70% / memory 80%
+- pdb.yaml                # minAvailable: 1
+- networkpolicy.yaml      # Egress restricted to aqp + aqp-admin + 443
+- external-secret.yaml    # Synced from Vault paths secret/data/aqp-ui/*
+- ingress.yaml            # aqp.fund + www.aqp.fund + app.aqp.fund + ws.aqp.fund
```

## Apply (staging)

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/base/aqp-ui
```

Or via the overlay (preferred):

```bash
kubectl apply -k aqp_platform/deployments/kubernetes/overlays/tower-dev/aqp-ui
```

## Cloudflare tunnel routes

Add three hostnames to the `cloudflare_edge` module's `ingress_rules`
in your environment's `main.tf` (e.g.
`aqp_platform/terraform/environments/tower/main.tf`):

```hcl
module "cloudflare_edge" {
  source = "../../modules/cloudflare_edge"
  # ...existing args...
  ingress_rules = [
    # ...existing rules for aqp.fund / api.aqp.fund / manage.aqp.fund...
    {
      hostname = "aqp.fund"
      service  = "http://aqp-ui.aqp-ui.svc.cluster.local:80"
    },
    {
      hostname = "www.aqp.fund"
      service  = "http://aqp-ui.aqp-ui.svc.cluster.local:80"
    },
    {
      hostname = "app.aqp.fund"
      service  = "http://aqp-ui.aqp-ui.svc.cluster.local:80"
    },
    {
      hostname = "ws.aqp.fund"
      service  = "http://aqp-core.aqp.svc.cluster.local:8000"
    },
  ]
}
```

## Cutover from `aqp-client`

`aqp.fund` currently routes to `aqp-client` (the Vite operator UI).
The aqp_ui rollout retires that public Ingress:

1. **Sprint 6 deploy**: apply the manifests above with the Ingress
   restricted to `staging.aqp.fund` (overlay
   `tower-dev/aqp-ui/patches/ingress-staging-hosts.yaml`).
2. **Smoke**: end-to-end Playwright run against `staging.aqp.fund` —
   marketing pages render, signup completes, dashboard reachable.
3. **Cutover**: replace `aqp-client/ingress.yaml`'s `aqp.fund` rule
   with a 301 to `aqp.fund` (no-op) and apply the production
   `aqp-ui/ingress.yaml` so `aqp.fund` now resolves to `aqp-ui`.
4. **Deprecation note**: `aqp_client/CUTOVER.md` records that
   `aqp-client` is now local-only and the public Ingress is removed.

## Boundaries

- AGENTS rule 1 of [aqp-platform.mdc](../../../../.cursor/rules/aqp-platform.mdc):
  No `import aqp.*` in this tree. Only Kustomize manifests + the
  matching Dockerfile under `aqp_platform/build/docker/aqp_ui/`.
- AGENTS rule 3: All secrets via ExternalSecret -> ClusterSecretStore
  -> Vault. Never inline in YAML.
- AGENTS rule 4: Multi-arch image (linux/amd64 + linux/arm64).
- AGENTS rule 5: Domain isolation. `aqp_ui` lives entirely under
  `aqp.fund` — never co-mingled with `julianwiley.com`.
