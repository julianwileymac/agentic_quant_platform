# OpenAPI specs (committed source-of-truth)

Two committed specs:

- `aqp.json` — the public AQP API at `api.aqp.fund` (created by
  `aqp.api.main.create_app().openapi()`).
- `control-plane.json` — the control-plane API at `manage.aqp.fund`
  (created by `aqp_cp.main.create_app().openapi()`).

## Drift detection

Every PR runs two checks (see [.github/workflows/ci.yml](../../.github/workflows/ci.yml)):

1. **`openapi-export`** — dumps the control-plane spec, then runs
   `oasdiff diff` against the committed `control-plane.json`. If
   the dumped spec drifts from the committed spec, the PR fails.
2. **`openapi-export-aqp`** — same shape for the main AQP API.

When you change a Pydantic model or add a route, the dumped spec
will diverge. Refresh the committed spec locally:

```powershell
# Control-plane
python -c "import json; from aqp_cp.main import create_app; \
    print(json.dumps(create_app().openapi(), indent=2))" \
    | Out-File -Encoding utf8 aqp_docs/openapi/control-plane.json

# Main API
python -c "import json; from aqp.api.main import create_app; \
    print(json.dumps(create_app().openapi(), indent=2))" \
    | Out-File -Encoding utf8 aqp_docs/openapi/aqp.json
```

Commit the refreshed JSON in the same PR.

## Breaking-change detection

Both jobs also run `oasdiff breaking` against `main`. If breaking
changes are detected, the PR comment notes that the
`breaking-change` label + a matching Changeset entry are required.
PR reviewers are responsible for confirming both.

## Versioning

Stripe-style date-epoch. First epoch: `2026-06-01`. New epochs:
add a new version line at `info.version`, leave the old spec
frozen, and serve both `/<epoch>/<path>` routes from the FastAPI
app. The 12-month sunset cycle uses RFC 8594 `Deprecation` +
`Sunset` headers.

## Rendering

Scalar renders the interactive playgrounds:

- [/reference/api/](https://docs.aqp.fund/reference/api/) — uses `aqp.json`
- [/reference/manage-api/](https://docs.aqp.fund/reference/manage-api/) — uses `control-plane.json`

`docusaurus-plugin-openapi-docs` ALSO emits one MDX file per
operation under `aqp_docs/docs/reference/api/<operation>.mdx` so
the docs site search + llms.txt index every endpoint.
