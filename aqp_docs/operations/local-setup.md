# Operations runbook — Local setup

This walks a brand-new developer from `git clone` to a running local AQP stack.

## Prerequisites

| Tool | Min version | Used for |
| --- | --- | --- |
| Python | 3.11 | AQP runtime + the new `aqp_platform_core` + `aqp_control_plane` packages |
| Node.js | 20 | Vite + legacy webui builds |
| pnpm | 9 | Frontend dep management (`corepack enable && corepack prepare pnpm@9.15.9 --activate`) |
| Docker | 25+ | Local compose stack + image builds |
| docker buildx | 0.13+ | Multi-arch image builds |
| Terraform | 1.10+ | Provisioning-only (rule 42) |
| k3d | 5.7+ | Local k3s cluster (for the Terraform-driven path) |
| kubectl | 1.30+ | Workload introspection |

## Step 1 — clone + install editable

```powershell
git clone https://github.com/julianwiley/agentic_quant_platform.git
cd agentic_quant_platform

python -m pip install -e .
python -m pip install -e ./aqp_platform_core[dev]
python -m pip install -e ./aqp_control_plane[dev,all-providers]
pnpm --dir aqp_client install
```

## Step 2 — generate `.env.local`

```powershell
make generate-config ENV=local
```

This reads [`aqp_platform/deployments/compose/.env.schema`](../../aqp_platform/deployments/compose/.env.schema) and writes `aqp_platform/deployments/compose/.env.local`. Open the file and fill in the `<set-via-secret-store>` placeholders for any service you plan to use.

## Step 3 — bring up the stack (two options)

### Option A — Docker Compose (new path, Phase 3 refactor)

```powershell
make dev
```

This brings up:
- `aqp-postgres` (pgvector)
- `redis-stack`
- `aqp-core` (FastAPI)
- `aqp-worker` (Celery)
- `aqp-client` (unified gateway, port 3000)

Once everything is `Up (healthy)`:

- Operator UI: <http://localhost:3000>
- Legacy Solara UI: <http://localhost:3000/legacy>
- OpenAPI: <http://localhost:3000/api/docs>

### Option B — Terraform + k3d (canonical, hard rule 42)

```powershell
aqp-cli deploy build      # build + push images to the local registry
aqp-cli deploy up         # terraform apply -> k3d cluster + workloads
aqp-cli deploy status     # pod + service rollup
aqp-cli deploy logs api   # tail aqp-api logs
```

`aqp-cli deploy *` is the existing path that lands every state mutation in `terraform_runs`. The Docker Compose path is friendlier for fast iteration but doesn't update the ledger.

## Step 4 — bring up the admin overlay (optional)

The `aqp_control_plane` micro-project runs on a separate Docker network (`aqp-admin`) so it's isolated from the workloads it manages.

```powershell
make dev-admin
```

After that, `curl http://localhost:9000/manage/health` should return `{"status": "ok", ...}`.

## Step 5 — verify

```powershell
make test                # all tests
make test-platform-core  # aqp_platform_core only
make test-providers      # aqp_control_plane provider contract tests
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `make generate-config ENV=local` errors with `missing required fields` | The schema parser caught a malformed block in `.env.schema`. Open the file, look for the entry above the error line, ensure every block has `key:` / `description:` / `required:` / `targets:` / `classification:`. |
| `docker compose up` fails with `port already in use` | The Vite dev server publishes 3001 by default; the compose stack publishes 3000. Stop whichever is running first or override via `docker-compose.override.yml`. |
| `pnpm --dir aqp_client build` runs out of memory | `NODE_OPTIONS=--max-old-space-size=4096 pnpm --dir aqp_client build`. |
| `aqp-cli deploy up` fails with `terraform binary not found` | `choco install terraform` (Windows) or set `AQP_TERRAFORM_BINARY=/path/to/terraform`. |
| `aqp_control_plane` shows `auth_disabled=true` in `/manage/health` | Set `AQP_AUTH_OIDC_ISSUER=https://your-tenant.us.auth0.com/` in `.env.local`, restart `aqp-cp`. |
