# Theia Cloud (Phase B)

Multi-tenant Theia operator manifests for the AQP IDE.

**STATUS: SCAFFOLDED BUT NOT DEPLOYED.** See [DEFERRED.md](DEFERRED.md)
for the trigger that flips this on.

## What this directory will own when deployed

| File | Purpose |
| --- | --- |
| [app-definition.yaml](app-definition.yaml) | `AppDefinition.theia.cloud/v1beta10` for the AQP IDE image |
| [values.example.yaml](values.example.yaml) | Helm values for the `theia-cloud` chart |
| [DEFERRED.md](DEFERRED.md) | Trigger criteria + Phase B contract |

## Phase B install (for when the trigger fires)

1. Install the three official Theia Cloud Helm charts:

   ```bash
   helm repo add theia-cloud https://eclipse-theia.github.io/theia-cloud-helm
   helm install theia-cloud-base   theia-cloud/theia-cloud-base   --namespace theia-cloud-system --create-namespace
   helm install theia-cloud-crds   theia-cloud/theia-cloud-crds   --namespace theia-cloud-system
   helm install theia-cloud        theia-cloud/theia-cloud        --namespace theia-cloud-system -f values.example.yaml
   ```

2. Apply the AQP IDE `AppDefinition`:

   ```bash
   kubectl apply -f app-definition.yaml
   ```

3. The Theia Cloud REST service then exposes a landing page where
   tenants can request per-user pods.

## Phase B trigger

See [DEFERRED.md](DEFERRED.md). The short version: ship Phase B when
≥2 internal AQP users need isolated workspaces.

## See also

- Phase A (this release): [../README.md](../README.md)
- AQP IDE roadmap: [../../../../aqp_docs/aqp-ide-roadmap.md](../../../../aqp_docs/aqp-ide-roadmap.md)
- Theia Cloud upstream: https://theia-cloud.io/
