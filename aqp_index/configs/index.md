# Configuration index

> Last refreshed: 2026-05-24 by aqp-index-curator (trigger: AQP IDE
> enhancement — extended to surface the AQP IDE's `AQP_THEIA_*` runtime
> env block and the `AQP_CLI_THEIA_*` operator-CLI settings).

## Canonical sources

- [../../configs/](../../configs/) - runtime YAML configs (strategies,
  agents, ML models, LLM profiles, RAG taxonomies, RL specs, paper
  trading, workflows).
- [../../aqp_platform/configs/](../../aqp_platform/configs/) -
  deployment-time YAML configs (`deployment/topology.yaml`,
  `terraform/*.yaml`).
- [../../aqp/config/settings.py](../../aqp/config/settings.py) - the
  single Pydantic settings class (AGENTS rule 7). Every `AQP_*` env var
  is a field. Topology fallback resolves
  `aqp_platform/configs/deployment/topology.yaml`.
- [../../aqp_cli/src/aqp_cli/config.py](../../aqp_cli/src/aqp_cli/config.py) -
  operator-CLI settings (`AQP_CLI_*` env prefix). Includes the
  `theia_port` / `theia_url` / `theia_workspace` / `theia_yarn_offline` /
  `theia_docker_image` fields consumed by `aqp-cli ide`.
- [../../aqp_ide/theia-extensions/aqp/src/node/aqp-config-endpoint.ts](../../aqp_ide/theia-extensions/aqp/src/node/aqp-config-endpoint.ts) -
  the AQP IDE's Node backend that translates `AQP_THEIA_*` env vars
  into the runtime JSON served on `GET /aqp/config`.
- [../../.env.example](../../.env.example) - template for local `.env`.

## Sections

| Section | Purpose |
| --- | --- |
| [deployment.md](deployment.md) | Deployment topology + Terraform stack config map + AQP IDE K8s overlay + `AQP_THEIA_*` env block |

## Split between runtime and deployment configs

| Where | Owns |
| --- | --- |
| [../../configs/](../../configs/) | Per-runtime specs the AQP process loads at boot or on-demand (AgentSpec, BotSpec, RLExperimentSpec, AnalysisSpec, StrategyConfig, ...). |
| [../../aqp_platform/configs/](../../aqp_platform/configs/) | Deployment-time inputs the platform consumes BEFORE the AQP process exists (cluster topology, IaC stack params). |
| [../../aqp_ide/browser.Dockerfile](../../aqp_ide/browser.Dockerfile) + [../../aqp_platform/deployments/kubernetes/aqp-ide/configmap-aqp.yaml](../../aqp_platform/deployments/kubernetes/aqp-ide/configmap-aqp.yaml) | `AQP_THEIA_*` runtime env block for the Theia Node backend (Auth0 SPA values, AQP API URLs, MCP URLs + audiences, copilot toggles). Served on `GET /aqp/config` per request — never baked into the JS bundle. |

## How to extend

Add a new file under `configs/` (runtime) only when a config domain
crosses three or more `aqp_*` packages or has a non-obvious overlay
pattern. Add a new file under `aqp_platform/configs/` (deployment) for
new cluster / topology / Terraform-stack inputs. New `AQP_THEIA_*` env
vars must be added in lockstep across **all five** locations enumerated
in [`.cursor/rules/aqp-ide.mdc`](../../.cursor/rules/aqp-ide.mdc) (the
TypeScript runtime config, the Node endpoint, the Dockerfile, the K8s
ConfigMap, and `_THEIA_ENV_KEYS` in the CLI).
