# AQP project index

> Last refreshed: 2026-05-23 (aqp_platform extraction) by plan execution;
> refresh owned by
> [aqp-index-curator](../.cursor/agents/aqp-index-curator.md).

## Top-level packages

| Package | Role | Canonical entry |
| --- | --- | --- |
| [aqp/](../aqp/) | Quant runtime (agents, RL, analysis, backtests, data, persistence, tasks) | [../AGENTS.md](../AGENTS.md) project map |
| [aqp_client/](../aqp_client/) | Active operator UI (Vite + React + Tailwind + shadcn) | [../aqp_client/AGENTS.md](../aqp_client/AGENTS.md) |
| [aqp_control_plane/](../aqp_control_plane/) | Standalone control plane (`/manage/*`, workload lifecycle) | [../aqp_control_plane/AGENTS.md](../aqp_control_plane/AGENTS.md) |
| [aqp_platform/](../aqp_platform/) | Hosted-platform deployment, build, IaC, cluster setup (single home) | [../aqp_platform/AGENTS.md](../aqp_platform/AGENTS.md) |
| [aqp_platform_core/](../aqp_platform_core/) | Shared value types, ABCs, auth + resource filters, topology | [../aqp_platform_core/AGENTS.md](../aqp_platform_core/AGENTS.md) |
| [aqp_bots/](../aqp_bots/) | Bot templates + BotRuntime | [../aqp_bots/AGENTS.md](../aqp_bots/AGENTS.md) |
| [aqp_snippets/](../aqp_snippets/) | Curated external-code knowledge | [../aqp_snippets/AGENTS.md](../aqp_snippets/AGENTS.md) |
| [aqp_cli/](../aqp_cli/) | Standalone operator CLI | [../aqp_cli/AGENTS.md](../aqp_cli/AGENTS.md) |
| [aqp_admin/](../aqp_admin/) | Internal admin (managed services + company accounts) | [../aqp_admin/AGENTS.md](../aqp_admin/AGENTS.md) |
| [aqp_ide/](../aqp_ide/) | Embedded Theia IDE (vendored) | [../aqp_ide/AGENTS.md](../aqp_ide/AGENTS.md) |
| [aqp_docs/](../aqp_docs/) | Canonical documentation | [../aqp_docs/index.md](../aqp_docs/index.md) |
| [aqp_index/](./) | **This index** (curator-owned SSoT) | [README.md](README.md) |

## Index sections

| Section | Purpose |
| --- | --- |
| [architecture/](architecture/) | SSoT architecture pointers |
| [configs/](configs/) | Consolidated configuration map |
| [code-index/](code-index/) | Token-saving per-module signatures |
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
