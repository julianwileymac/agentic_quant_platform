# AQP IDE

The **AQP IDE** is a white-labeled Eclipse Theia 1.72 distribution + six
AQP compile-time extensions + an MCP-driven research copilot + a
Perspective Arrow notebook renderer. It is the developer environment
that sits next to (not replaces) the `aqp_client/` Vite operator UI.

## SSoT pointers

This page is a thin pointer into the in-folder documentation that lives
in `aqp_ide/`. The canonical contracts are there.

| Topic | Path |
| --- | --- |
| Overview + architecture | [../aqp_ide/README.md](../aqp_ide/README.md) |
| Process + extension architecture | [../aqp_ide/docs/architecture.md](../aqp_ide/docs/architecture.md) |
| Per-extension reference | [../aqp_ide/docs/extensions.md](../aqp_ide/docs/extensions.md) |
| Canonical operator entrypoint (`aqp-cli ide`) | [../aqp_ide/docs/cli-entrypoint.md](../aqp_ide/docs/cli-entrypoint.md) |
| MCP integration (RFC 9728 + RFC 8707) | [../aqp_ide/docs/mcp-integration.md](../aqp_ide/docs/mcp-integration.md) |
| Research Copilot (chat agent) | [../aqp_ide/docs/research-copilot.md](../aqp_ide/docs/research-copilot.md) |
| Notebook (Perspective MIME renderer) | [../aqp_ide/docs/notebook.md](../aqp_ide/docs/notebook.md) |
| Quant widgets (SpecAuthor / RunInspector / BacktestRunner) | [../aqp_ide/docs/quant-widgets.md](../aqp_ide/docs/quant-widgets.md) |
| Deployment (local / single-pod K8s / Theia Cloud) | [../aqp_ide/docs/deployment.md](../aqp_ide/docs/deployment.md) |
| Phased roadmap (blueprint → AQP) | [aqp-ide-roadmap.md](aqp-ide-roadmap.md) |

## Hard-rule touchpoints

The AQP IDE most-cited hard rules from [../AGENTS.md](../AGENTS.md):

| Rule | Owner | AQP IDE consumer |
| --- | --- | --- |
| 2 (LLM gateway) | `aqp/llm/providers/router.py::router_complete` | `aqp-research-copilot-ext`'s `RouterCompleteClient` |
| 4 (canonical progress frame) | `aqp/tasks/_progress.py::emit` | `aqp-quant-ext`'s `AqpWsClient` / `RunInspectorWidget` |
| 22 (DataMCP boundary) | `aqp/data/mcp/` | `aqp-mcp-bridge-ext`'s registrations |
| 26 (CredentialResolver) | `aqp/credentials/resolver.py` | Python notebook helpers (`aqp/notebook/helpers.py`) |
| 27 (IdentityProvider) | `aqp/auth/providers/` | `aqp-ext`'s `Auth0Service` + new MCP bridge / copilot |
| 45 (WorkloadRuntime) | `aqp_platform_core/runtime/workload.py` | `aqp-ext`'s halt fan-out + `aqp-cli ide` doctor |
| 47 (topology) | `aqp_control_plane/services/topology.py` | `aqp-cli ide url --remote` / `detect` / `env` |
| 49 (MCP audience, RFC 8707) | `aqp/api/well_known.py` + `aqp/api/mcp_audience.py` | `aqp-mcp-bridge-ext`'s `X-AQP-MCP-Audience` header |
| 52 (step-up MFA) | `aqp/api/security_stepup.py` | `aqp-ext`'s halt command + future copilot write tools |

## Canonical operator entrypoint

```bash
aqp-cli auth login --device   # RFC 8628 device flow + OS keyring (rule 53)
aqp-cli ide install           # one-time bootstrap
aqp-cli ide build --dev       # yarn build:extensions + build:applications:dev
aqp-cli ide start --open      # spawn Theia + open in browser
aqp-cli ide doctor            # preflight checks
```

Full CLI reference: [../aqp_cli/docs/index.md](../aqp_cli/docs/index.md).

## Boundary contract (mirrored from `.cursor/rules/aqp-ide.mdc`)

- `aqp_ide/` extensions MUST NOT `import` from `agentic_quant_platform`
  source. Cross HTTP only (`AqpApiService`) or via the DataMCP /
  CodebaseMCP HTTP surfaces.
- AQP-specific behavior lives ONLY under
  `aqp_ide/theia-extensions/aqp*/` (the six extensions). Don't sprinkle
  AQP imports into core Theia files.
- The IDE is browser-target-only. The Electron app remains
  upstream-oriented and is NOT wired for AQP in this release.
- The canonical entrypoint is `aqp-cli ide`. Direct `yarn` invocations
  are inner-loop development only.

## Vendored workspace retirement

The vendored `test_theia/theia-ide` workspace is byte-for-byte identical
to `aqp_ide/` and can be retired. See
[../aqp_ide/docs/retire-vendored-workspace.md](../aqp_ide/docs/retire-vendored-workspace.md)
for the 5-step checklist.
