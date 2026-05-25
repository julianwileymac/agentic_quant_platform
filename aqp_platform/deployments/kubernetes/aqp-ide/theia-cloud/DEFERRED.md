# Theia Cloud — deferred to Phase B

This directory is **scaffolded but NOT deployed** in the current release.

## Trigger to flip on

Ship Phase B (install the Theia Cloud operator + apply the
`AppDefinition` here) when **at least one** of the following becomes
true:

1. ≥2 internal AQP users need isolated workspaces concurrently and the
   single-pod overlay at `../` can't be shared.
2. An AQP customer requires per-tenant resource isolation for the IDE
   (memory / CPU / GPU quotas per user).
3. The AQP IDE needs GPU-backed pods (LLM-driven factor research,
   RAPIDS-accelerated EDA) — the Theia Cloud operator's
   `AppDefinition.resources` makes per-image GPU node selectors
   trivial.

Until then, the single-pod deployment at
[../deployment.yaml](../deployment.yaml) is sufficient and operationally
simpler.

## Contract when flipped on

Phase B MUST NOT regress Phase A. Concretely:

- The single-pod overlay continues to work; Theia Cloud is an
  alternative deployment, not a replacement.
- The same Docker image (`aqp/aqp-ide:<tag>`) backs both deployments.
  This is the contract the `aqp_ide/browser.Dockerfile` enforces.
- The Auth0 SPA `client_id`, AQP API URL, and MCP URLs all come from
  the same `ConfigMap` shape; the Theia Cloud operator just projects
  them into the per-session pod.
- The same `aqp-cli ide doctor` runs against Theia Cloud pods (over
  `kubectl port-forward` or via Cloudflare Access).

## Phase B implementation pointer

When the trigger fires, mirror the EclipseSource reference deployment
at https://theia-cloud.io/documentation/. The plan to follow:

1. Install the three official Helm charts (`theia-cloud-base`,
   `theia-cloud-crds`, `theia-cloud`).
2. Apply the `AppDefinition` here.
3. Update the `aqp-cli ide` CLI to expose `aqp-cli ide tenant create`
   / `tenant destroy` subcommands that POST to the Theia Cloud REST
   service.
4. Tear down or down-scale the single-pod overlay at `../`.

Cross-link: [../../../../aqp_docs/docs/concepts/infrastructure/aqp-ide-roadmap.md](../../../../aqp_docs/docs/concepts/infrastructure/aqp-ide-roadmap.md)
Phase B section.
