# AGENTS.md

Agent contract for `theia-ide-aqp-notebook-quant-ext`.

## Purpose

Two quant-focused notebook capabilities that the upstream Theia notebook
system does not ship:

1. **FINOS Perspective MIME renderer** for the AQP-flavoured MIME type
   `application/vnd.aqp.perspective-arrow+arrow`. Kernels (Python, R, etc.)
   that emit this MIME type stream raw Arrow record batches into a
   `<perspective-viewer>` instance embedded directly in the notebook
   output area.
2. **AQP Notebook scaffolder** — a `File → New AQP Notebook` command that
   creates a blank `.ipynb` with a first cell pre-populated by an `import`
   statement against `aqp.notebook.helpers` (which auto-binds the active
   AQP tenancy, DataMCP client, and Arrow Flight client to Python globals).

## Hard boundaries

1. The MIME renderer MUST NOT issue HTTP requests of its own — it receives
   Arrow bytes from the kernel and renders them. All data fetching happens
   in the kernel via `aqp.notebook.helpers`.
2. The scaffolder MUST emit `.ipynb` JSON that is byte-compatible with the
   standard Jupyter notebook format. The first cell MUST be plain Python
   imports — no magics, no `%%javascript`.
3. No `import` from `agentic_quant_platform` TypeScript source. The Python
   helpers in `aqp/notebook/helpers.py` are referenced by string (it's the
   kernel that imports them at runtime), never by TypeScript import.
4. Cross-extension dependency on `theia-ide-aqp-ext` (for
   `AqpTenancyStore` and `AqpConfigService`) is allowed.

## Validation

```bash
yarn build:extensions
yarn build:applications:dev
```

After build, verify in the running IDE:
- `File → New AQP Notebook` is present.
- Creating a new AQP notebook scaffolds a file with the helper imports cell.
- Running a Python cell that emits `application/vnd.aqp.perspective-arrow+arrow`
  renders an interactive Perspective grid in the output area.
- The renderer survives a notebook reload (Perspective is mounted lazily so
  multiple cells with the same MIME type each get their own grid).
