# Architecture index

> Last refreshed: 2026-05-24 by aqp-index-curator (trigger: AQP IDE
> enhancement — added the [aqp-ide.md](aqp-ide.md) cross-package
> pointer; the IDE crosses `aqp_ide/`, `aqp_cli/`, `aqp_platform/`,
> `aqp_docs/`, and `aqp/notebook/`).

This page is intentionally a list of pointers. Canonical prose lives in
[../../aqp_docs/](../../aqp_docs/). When two sources disagree, the file
linked here is authoritative for architecture; the prose remains
authoritative for the underlying mechanism.

## Sections

| Concept | SSoT pointer |
| --- | --- |
| Repository boundaries | [boundaries.md](boundaries.md) |
| Runtime contracts (Agent / Bot / RL / Analysis / Workflow / Terraform / Workload) | [runtimes.md](runtimes.md) |
| Data flow (catalog / DataMCP / Iceberg / Hudi / QuestDB) | [data-flow.md](data-flow.md) |
| AQP IDE (Theia 1.72 + six extensions + `aqp-cli ide`) | [aqp-ide.md](aqp-ide.md) |

## How to extend

Add a new file under `architecture/` only when an architectural concept
crosses three or more `aqp_*` packages. Single-package concerns belong
in that package's own AGENTS.md / docs.
