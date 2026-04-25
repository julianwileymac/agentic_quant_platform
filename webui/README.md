# aqp webui

Next.js 15 + TypeScript frontend for the Agentic Quant Platform.

Replaces the legacy Solara UI on `:8765`. Talks to the FastAPI backend on `:8000`
over REST + WebSocket, with type-safe access generated from FastAPI's OpenAPI spec.

## Stack

- Next.js 15 (App Router) + React 19 + TypeScript strict
- Ant Design 5 + `@ant-design/icons` + `@ant-design/charts`
- AG Grid Community for tabular surfaces
- React Flow v12 (`@xyflow/react`) for visual workflow editors
- `react-financial-charts` for OHLC + indicator overlays
- `recharts` for general line/bar/area
- TanStack Query v5 + Zustand
- `openapi-typescript` + `openapi-fetch`

## Quick start

```bash
# from repo root
make webui-install   # one-time pnpm install
make webui-gen-api   # dump openapi.json + regenerate TS client
make webui-dev       # start dev server on :3000

# or directly
cd webui
pnpm install
pnpm dev
```

The app expects the FastAPI backend on `http://localhost:8000`. Override with
`NEXT_PUBLIC_API_URL` in `webui/.env.local`.

## Layout

```
webui/
  app/                    # App Router routes
    (shell)/              # Authenticated app shell (Sidebar + TopBar)
    api/                  # Server route handlers (BFF)
  components/
    shell/                # Sidebar, TopBar, CommandK
    data-grid/            # AG Grid wrappers
    flow/                 # React Flow node + edge primitives
    charts/               # OHLC, Equity, Heatmap, Sparkline, FanChart
    chat/                 # Threaded chat + streaming components
    forms/                # react-hook-form + Ant bindings
  lib/
    api/                  # Typed OpenAPI client + TanStack Query hooks
    ws/                   # WebSocket hooks (chat, live market)
    theme/                # Antd token + dark mode
    store/                # Zustand slices
    hooks/
```
