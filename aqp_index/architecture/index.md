# Architecture index

> Last refreshed: 2026-05-23 (seed). SSoT map of canonical architecture docs.

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

## How to extend

Add a new file under `architecture/` only when an architectural concept
crosses three or more `aqp_*` packages. Single-package concerns belong
in that package's own AGENTS.md / docs.
