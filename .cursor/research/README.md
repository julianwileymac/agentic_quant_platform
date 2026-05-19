# Tavily research — pending user auth

Tavily CLI is installed (v0.1.2) at:

```
C:\Users\Julian Wiley\AppData\Roaming\Python\Python314\Scripts\tvly.exe
```

It is NOT on PATH and is NOT authenticated. To unblock the seven research runs queued by the AQP control-plane refactor plan ([Phase 0](../../docs/architecture/decisions/004-provider-abstraction.md)):

1. **In a real PowerShell session** (not the Cursor agent shell) add Scripts to PATH for this session:
   ```powershell
   $env:Path = "$env:APPDATA\Python\Python314\Scripts;$env:Path"
   tvly --version   # should print: tavily-cli 0.1.2
   ```
2. **Authenticate** — pick one:
   ```powershell
   tvly login                    # OAuth in browser
   tvly login --api-key tvly-<YOUR_KEY>
   $env:TAVILY_API_KEY = "tvly-<YOUR_KEY>"   # session-only
   ```
3. **Confirm** — `tvly --status` should report `Authenticated`.
4. **Run the seven reports** (commands from the original planning prompt):

   ```powershell
   tvly research --model pro --stream -o ".cursor\research\01_control_plane_pattern_2026.md" `
     "Best practices in 2026 for designing a separate isolated control-plane container alongside a workload plane in hybrid docker-compose and Kubernetes deployments. Compare patterns from Kubernetes itself, ArgoCD, Flux, Crossplane, Backstage, and Kratix. Focus on: provider abstraction across docker / k8s / EKS / AKS / GKE, JWT-based RBAC at the API boundary, telemetry streaming over WebSocket, and how to ship the control plane as both a docker-compose service and a Kubernetes Deployment from the same image."

   tvly research --model pro --stream -o ".cursor\research\02_auth0_zero_trust_2026.md" `
     "2026 best practices for a two-layer Auth0 architecture in a Next.js 15 + FastAPI platform: SPA + API audience model, Authorization Code with PKCE, M2M tokens for service-to-service, claim namespacing for roles + resources + org_id, JWKS caching, scope-based RBAC, and Post-Login Actions that inject resource ownership claims. Include guidance on resource-scoped filtering server-side and how to render permission-aware UI in Next.js using @auth0/nextjs-auth0 v4 hooks. Compare with Clerk and Descope where relevant."

   tvly research --model mini -o ".cursor\research\03_nextjs_static_export_fastapi.md" `
     "Best practice in 2026 for serving a Next.js 15 static export from inside a FastAPI application: directory layout, asset hashing, client-side routing fallback, mounting legacy Solara as an ASGI sub-app on the same FastAPI instance, and websocket proxying with reconnect / backoff."

   tvly research --model mini -o ".cursor\research\04_kubernetes_security_hardening_2026.md" `
     "Kubernetes 2026 pod security hardening checklist for Python ML workloads: runAsNonRoot, readOnlyRootFilesystem, distroless or minimal base images, securityContext, NetworkPolicies, PodDisruptionBudget, HorizontalPodAutoscaler with custom metrics, mounting Docker socket read-only inside a control plane, and StatefulSet patterns for Redis Stack with persistent volumes."

   tvly research --model pro --stream -o ".cursor\research\05_provider_abstraction_multi_cloud_2026.md" `
     "Designing an abstract InfrastructureProvider Python ABC in 2026 that targets docker-compose, Kubernetes (in-cluster + kubeconfig), AWS (EKS + ECS Fargate via boto3), Azure (AKS + Container Instances via azure-mgmt SDK), and GCP (GKE + Cloud Run via google-cloud-run). Cover credential chain handling, exception normalisation, async generator pattern for metric streaming, and contract testing across all five backends with mocked SDKs."

   tvly research --model mini -o ".cursor\research\06_repo_split_monolith_to_micro.md" `
     "How to split a Python monorepo so that a sub-package (e.g. aqp_control_plane/) can be released independently while sharing zero runtime imports with the parent (aqp/) — Hatch / Poetry / uv workspaces in 2026, internal vs published packages, shared model contracts via openapi.json or protobuf, and CI/CD pipelines that build both as standalone container images."

   tvly research --model mini -o ".cursor\research\07_kustomize_overlays_helm_charts.md" `
     "2026 guidance on combining Kustomize overlays (dev / staging / prod) with Helm charts for FastAPI + Redis + worker deployments. Cover: image tag overrides per overlay, HPA bounds per env, ConfigMap interpolation, sealed-secrets vs external-secrets-operator, and using kustomize.io as the final layer over Helm-rendered base manifests."
   ```

The reports are NOT a hard precondition for any later phase. The plan itself encodes the architectural decisions; the research runs are due-diligence corroboration that can land in a follow-up PR.

## What the refactor decisions already encode (without research)

- **Phase 1 shared library pattern** — matches the well-established `internal/` Go convention adapted for Python
- **Phase 3 single-container client** — see [ADR 002](../../docs/architecture/decisions/002-single-container-client.md)
- **Phase 4 two-layer Auth0** — see [ADR 003](../../docs/architecture/decisions/003-auth0-zero-trust.md)
- **Phase 4 namespace rename** — `https://aqp/` → `https://aqp.internal/` with one-release alias (`auth_claims_namespace_aliases`)
- **Phase 5 provider abstraction** — see [ADR 004](../../docs/architecture/decisions/004-provider-abstraction.md)
- **Phase 5 isolation boundary** — see [ADR 005](../../docs/architecture/decisions/005-separated-control-plane.md)
- **Phase 6 Pod Security Standards "restricted"** — `runAsNonRoot`, `readOnlyRootFilesystem`, `drop ALL` capabilities
