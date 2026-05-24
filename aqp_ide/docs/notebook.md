# AQP IDE notebook integration

The AQP IDE ships two quant-focused notebook capabilities via
[`theia-ide-aqp-notebook-quant-ext`](../theia-extensions/aqp-notebook-quant/):

1. **FINOS Perspective MIME renderer** for streaming Arrow record batches
   from Python kernels into an embedded interactive grid.
2. **AQP Notebook scaffolder** (`File → New AQP Notebook`) that creates a
   blank `.ipynb` pre-populated with an `import` of
   `aqp.notebook.helpers`.

## Perspective Arrow MIME renderer

### Why this matters

Per the blueprint §4.5 + §2.6, the Perspective MIME renderer is the
single highest-value notebook-only feature for a quant IDE — million-row
tick datasets pivot and filter in ~100 ms inside the notebook output area
without leaving the cell.

### MIME envelope

```
application/vnd.aqp.perspective-arrow+arrow
```

Python kernels emit bytes under this MIME via the helper:

```python
from aqp.notebook.helpers import attach
ctx = attach()
# my_arrow_table is a pyarrow.Table
display(ctx.perspective(my_arrow_table), raw=True)
```

The Theia notebook system routes the bytes to the registered renderer,
which mounts a `<perspective-viewer>` Custom Element in the cell output
area and pushes the Arrow IPC bytes directly into Perspective's WASM
engine. No JSON serialisation, no extra round-trip.

### Renderer source

[`src/browser/notebook/perspective-mime-renderer.ts`](../theia-extensions/aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts)

The renderer lazy-loads `@finos/perspective` + the two viewer plugins on
first use. If the dynamic import fails (e.g. a stripped-down build), the
renderer falls back to a textual preview showing the byte count + MIME
type so the operator always sees something useful.

## AQP Notebook scaffolder

### Command

`File → New AQP Notebook` (or `AQP: New Notebook` in the command palette).

### First cell (verbatim)

```python
# AQP notebook scaffolded by theia-ide-aqp-notebook-quant-ext.
# The aqp.notebook.helpers module attaches the active AQP tenancy and
# returns ergonomic clients for DataMCP, CodebaseMCP, Arrow Flight, and
# the AQP REST API. Secrets resolve through CredentialResolver (AQP rule 26).
from aqp.notebook.helpers import attach

ctx = attach()
data = ctx.data           # DataMCP-backed catalog client
codebase = ctx.codebase   # CodebaseMCP-backed search/navigation client
router = ctx.router       # AQP router_complete LLM gateway (rule 2)

print('AQP notebook attached to', ctx.tenancy_summary())
```

The file is created in the active workspace as
`aqp-notebook-<timestamp>.ipynb` and immediately opened in the editor.

## The Python helpers (`aqp/notebook/helpers.py`)

Shipped as part of the AQP monolith. Public surface:

| Symbol | Type | Purpose |
| --- | --- | --- |
| `attach(*, org?, team?, workspace?, project?, lab?)` | function | Build an `AqpNotebookContext` for the active tenancy |
| `AqpNotebookContext.data` | property | DataMCP-backed catalog client (rule 22) |
| `AqpNotebookContext.codebase` | property | CodebaseMCP-backed search / navigation client |
| `AqpNotebookContext.router` | property | `router_complete` LLM gateway facade (rule 2) |
| `AqpNotebookContext.perspective(table)` | method | Wrap a `pyarrow.Table` in the AQP Perspective MIME envelope |
| `AqpNotebookContext.tenancy_summary()` | method | One-line description of the active tenancy (never includes secrets) |

Hard-rule contract:

- Credentials resolve through `CredentialResolver` (AQP rule 26).
- LLM calls route through `router_complete` (AQP rule 2).
- DataMCP / CodebaseMCP access goes through the bundled in-process
  bridges or stdio binaries (AQP rule 22).
- Secrets NEVER appear in `tenancy_summary()` output — the redaction
  filter strips any attribute whose name resembles a credential key.

## Environment passthrough

When the Theia browser scaffolder spawns a Python kernel, the kernel
inherits these env vars (set by the Theia backend per
[`aqp-config-endpoint.ts`](../theia-extensions/aqp/src/node/aqp-config-endpoint.ts)):

| Env var | Default | Use |
| --- | --- | --- |
| `AQP_ORG`, `AQP_TEAM`, `AQP_WORKSPACE`, `AQP_PROJECT`, `AQP_LAB` | (unset) | Tenancy passthrough for `attach()` |

Set per-session via `AQP: Set Tenancy` in the Theia command palette.

## See also

- [extensions.md](extensions.md)
- `aqp_docs/data-mcp.md` (DataMCP boundary)
- `aqp_docs/credentials.md` (CredentialResolver)
- FINOS Perspective docs: https://perspective.finos.org/
- Apache Arrow IPC: https://arrow.apache.org/docs/format/Columnar.html
