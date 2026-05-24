# theia-ide-aqp-notebook-quant-ext

AQP quant notebook extras: a **FINOS Perspective MIME renderer** for
streaming Arrow record batches from Python kernels into an interactive
WASM grid, plus a **New AQP Notebook** scaffolder.

## The Perspective Arrow MIME renderer

Per the blueprint §4.5 + §2.6, this is the single highest-value
notebook-only feature for a quant IDE. The flow:

1. A Python notebook cell builds an Arrow `Table` / `RecordBatch` via
   `aqp.notebook.helpers.preview(...)` or any pyarrow / polars output.
2. The helper wraps the bytes in the MIME envelope
   `application/vnd.aqp.perspective-arrow+arrow`.
3. Theia's notebook system pipes the bytes to the registered renderer
   bundled with this extension.
4. The renderer mounts a `<perspective-viewer>` Custom Element in the
   output area and pushes the Arrow bytes directly into Perspective's
   WASM engine — no JSON serialisation, no extra round-trip.

Result: million-row tick datasets that render and pivot in ~100 ms inside
the notebook.

## The 'New AQP Notebook' command

`File → New AQP Notebook` (or `AQP: New Notebook` in the command palette)
creates a fresh `.ipynb` in the active workspace with a first cell:

```python
# AQP notebook — scaffolded by theia-ide-aqp-notebook-quant-ext
from aqp.notebook.helpers import attach
ctx = attach()  # binds the active AQP tenancy + DataMCP client + Arrow Flight
data = ctx.data
codebase = ctx.codebase
```

The Python helpers live in the AQP monolith at `aqp/notebook/helpers.py`
and resolve credentials via `CredentialResolver` (AQP rule 26). They
NEVER print secret material.

## Files

- [src/browser/aqp-notebook-quant-frontend-module.ts](src/browser/aqp-notebook-quant-frontend-module.ts)
- [src/browser/notebook/perspective-mime-renderer.ts](src/browser/notebook/perspective-mime-renderer.ts)
- [src/browser/notebook/aqp-notebook-scaffolder.ts](src/browser/notebook/aqp-notebook-scaffolder.ts)
- [src/browser/commands/aqp-notebook-contribution.ts](src/browser/commands/aqp-notebook-contribution.ts)
- [src/node/aqp-notebook-quant-backend-module.ts](src/node/aqp-notebook-quant-backend-module.ts)
- [src/common/aqp-notebook-protocol.ts](src/common/aqp-notebook-protocol.ts)

## See also

- [../../docs/notebook.md](../../docs/notebook.md)
- The Python helpers contract: `aqp/notebook/helpers.py`
- `aqp_docs/data-mcp.md` (DataMCP, AQP rule 22)
