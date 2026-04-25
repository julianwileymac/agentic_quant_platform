# webui — Next.js 15 frontend

The `webui/` package is the React/TypeScript replacement for the legacy Solara
UI on `:8765`. It runs as a separate Node process on `:3000` and talks to the
FastAPI backend on `:8000` over REST + WebSocket.

## Stack

- Next.js 15 App Router, React 19, TypeScript strict
- Ant Design 5 + `@ant-design/icons` + `@ant-design/charts`
- AG Grid Community (`ag-grid-community` + `ag-grid-react`)
- React Flow v12 (`@xyflow/react`) for visual workflow editors
- `react-financial-charts` for OHLC + indicators (alongside `recharts`)
- TanStack Query v5 + Zustand
- `openapi-typescript` + `openapi-fetch` for type-safe REST access

The full directory layout and design rationale live in `webui/README.md`.

## Local dev

From the repo root:

```bash
make webui-install   # one-time pnpm install
make webui-gen-api   # dump OpenAPI + regenerate TypeScript client
make webui-dev       # start dev server on :3000
```

The Next dev server proxies `/aqp-api/*` → `${NEXT_PUBLIC_API_URL}` (default
`http://localhost:8000`) so cookies and WebSockets stay same-origin in dev.

## Backend contract additions

The refactor added or extended a small surface on the FastAPI side:

- `GET  /auth/whoami` — local-first identity stub
- `GET  /chat/threads`, `POST /chat/threads`, `DELETE /chat/threads/{id}`
- `POST /chat` accepts an optional `context: ChatContext` block (page,
  vt_symbol, backtest_id, strategy_id, …) which is materialised into the
  system prompt so the assistant knows which page the user is on.
- CORS is now driven by `AQP_WEBUI_CORS_ORIGINS` (comma-separated list).
  Empty value falls back to the legacy `"*"` behaviour.

WebSocket contracts are unchanged:

- `WS /chat/stream/{task_id}` — Celery task progress
- `WS /live/stream/{channel_id}` — live market subscriptions

## OpenAPI client regeneration

The `webui` consumes a generated `paths` interface that mirrors FastAPI's
spec exactly:

1. `python -m scripts.export_openapi --out data/openapi.json`
2. `pnpm --dir webui exec openapi-typescript ../data/openapi.json -o lib/api/generated/schema.d.ts`

`make webui-gen-api` (or `pwsh ./scripts/gen_webui_client.ps1`) wraps both
steps. CI should run them and fail if the diff is non-empty (drift check).

## Strangler migration

During the migration both UIs run in parallel:

- `:3000` — Next.js webui (new, primary)
- `:8765` — Solara UI (legacy)
- `/dash`  — Dash strategy monitor (kept; embedded in Next via iframe under `/monitor`)

When the Next.js app reaches feature parity:

1. Drop the `ui` service from `docker-compose.yml`.
2. Delete `aqp/ui/pages/` and `aqp/ui/app.py` (keep the Dash factory).
3. Optionally relax `fastapi<0.116` and `starlette<0.46` pins in
   `pyproject.toml` (they exist solely to satisfy Solara).
