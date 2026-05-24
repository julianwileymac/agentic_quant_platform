# AQP project index

> Last refreshed: 2026-05-24 by aqp-index-curator (trigger: AQP IDE
> enhancement landing six Theia extensions, `aqp-cli ide` entrypoint,
> single-pod K8s overlay, Phase A docs + Cursor governance artefacts).

## Top-level packages

| Package | Role | Canonical entry |
| --- | --- | --- |
| [aqp/](../aqp/) | Quant runtime (agents, RL shim, analysis, backtests, data, persistence, tasks). Now also hosts [`aqp/notebook/`](../aqp/notebook/) helpers consumed by the AQP IDE's notebook scaffolder. | [../AGENTS.md](../AGENTS.md) project map |
| [aqp_client/](../aqp_client/) | Active operator UI (Vite + React + Tailwind + shadcn) | [../aqp_client/AGENTS.md](../aqp_client/AGENTS.md) |
| [aqp_control_plane/](../aqp_control_plane/) | Standalone control plane (`/manage/*`, workload lifecycle) | [../aqp_control_plane/AGENTS.md](../aqp_control_plane/AGENTS.md) |
| [aqp_platform/](../aqp_platform/) | Hosted-platform deployment, build, IaC, cluster setup (single home). Now also hosts the [`aqp-ide/`](../aqp_platform/deployments/kubernetes/aqp-ide/) single-pod K8s overlay. | [../aqp_platform/AGENTS.md](../aqp_platform/AGENTS.md) |
| [aqp_platform_core/](../aqp_platform_core/) | Shared value types, ABCs, auth + resource filters, topology | [../aqp_platform_core/AGENTS.md](../aqp_platform_core/AGENTS.md) |
| [aqp_bots/](../aqp_bots/) | Bot templates + BotRuntime | [../aqp_bots/AGENTS.md](../aqp_bots/AGENTS.md) |
| [aqp_rl/](../aqp_rl/) | RL subsystem (`RLRuntime`, `RLComponent` metaclass, advantage estimators, weight-centric pipeline, Iceberg trajectory store) | [../aqp_rl/AGENTS.md](../aqp_rl/AGENTS.md) |
| [aqp_models/](../aqp_models/) | Custom model boundary (ML framework, Predictor Hub, AlphaBacktestExperiment, finetune trainers, vLLM + Ollama serving) | [../aqp_models/AGENTS.md](../aqp_models/AGENTS.md) |
| [aqp_snippets/](../aqp_snippets/) | Curated external-code knowledge | [../aqp_snippets/AGENTS.md](../aqp_snippets/AGENTS.md) |
| [aqp_cli/](../aqp_cli/) | Standalone operator CLI. Now also hosts the [`ide`](../aqp_cli/src/aqp_cli/commands/ide.py) command group (`install` / `build` / `start` / `stop` / `status` / `logs` / `open` / `url` / `env` / `detect` / `doctor`). | [../aqp_cli/AGENTS.md](../aqp_cli/AGENTS.md) |
| [aqp_admin/](../aqp_admin/) | Internal admin (managed services + company accounts) | [../aqp_admin/AGENTS.md](../aqp_admin/AGENTS.md) |
| [aqp_ide/](../aqp_ide/) | White-labeled Theia 1.72 + **six** AQP compile-time extensions (`aqp`, `aqp-shell`, `aqp-mcp-bridge`, `aqp-research-copilot`, `aqp-notebook-quant`, `aqp-quant`). Canonical operator entrypoint is `aqp-cli ide`. | [../aqp_ide/AGENTS.md](../aqp_ide/AGENTS.md) + [../aqp_docs/aqp-ide.md](../aqp_docs/aqp-ide.md) |
| [aqp_docs/](../aqp_docs/) | Canonical documentation | [../aqp_docs/index.md](../aqp_docs/index.md) |
| [aqp_index/](./) | **This index** (curator-owned SSoT) | [README.md](README.md) |

## Index sections

| Section | Purpose |
| --- | --- |
| [architecture/](architecture/) | SSoT architecture pointers (boundaries, runtimes, data flow, AQP IDE) |
| [configs/](configs/) | Consolidated configuration map (deployment + IDE env block) |
| [code-index/](code-index/) | Token-saving per-module signatures (now includes the six IDE extensions + `aqp/notebook/`) |
| [skills/](skills/) | Project skills registry + extension guidance |
| [subagents/](subagents/) | Subagent registry + extension guidance |

## Refresh cadence

- The curator runs after any commit touching one of:
  [../AGENTS.md](../AGENTS.md), [../.cursor/rules/](../.cursor/rules/),
  [../aqp_docs/](../aqp_docs/), [../configs/](../configs/), or the
  public surface of any `aqp_*` package.
- Each file under this tree carries a `> Last refreshed: <date>` line.
  If a file's date is older than the most recent qualifying commit, the
  curator owns the gap.
