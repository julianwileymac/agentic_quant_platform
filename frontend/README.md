# aqp frontend

Vite 7 + React 19 + TypeScript 5.9 + Tailwind CSS 4 + shadcn/ui. The
new operator-grade UI for the Agentic Quant Platform; runs in parallel
with the legacy `webui/` Next.js application until route parity is
reached and the cutover is performed.

## Stack

- Vite 7, React 19 RC, TypeScript 5.9 strict
- Tailwind CSS 4 + shadcn/ui (Radix primitives), tw-animate-css
- React Router 7 data routers
- TanStack Query 5 + Zustand 5
- `lightweight-charts` 4 (WebGL OHLC), D3 7, ECharts 5, Recharts
- AG Grid Community 32, `@xyflow/react` 12, CodeMirror 6
- `openapi-fetch` (reuses `webui/lib/api/generated/schema.d.ts`)
- Vitest + Testing Library, Playwright
- Biome lint + format (single tool, replaces ESLint + Prettier)

## What ships today (Phases 0 – 6, full route parity)

- **Throttled WebSocket pipeline** — `src/lib/ws/throttle.ts` collapses
  microsecond-cadence WS traffic to ~30 FPS via a `requestAnimationFrame`
  batcher with a bounded ring buffer. Recency wins over completeness.
- **Live Trading Desk** at `/live` — resizable split panes, WebGL OHLC
  via `lightweight-charts`, virtualized two-sided order book, manual
  order ticket gated by typed-confirmation friction, working orders +
  positions + tape tabs.
- **Action Center** at `/action-center` (and modal from the topbar bell)
  — subscribes to `/agents/proposals/stream` once at the App root, fires
  high-priority toasts on every new proposal, renders LTL guardrail
  outcomes + cost-cap remaining + risk metrics with semantic +/- colour
  coding, approves / declines through `AgentRuntime` so `agent_runs_v2`
  rows update.
- **Kill-switch** in the TopBar — fans out POSTs to `/agents/halt`,
  `/paper/stop-all`, `/bots/halt-all`, `/rl/halt-all` after a typed
  `HALT` confirmation.
- **Sandbox / Paper mode** global banner — amber outline around the
  application body, `[SANDBOX]` / `[PAPER]` prefix on the document
  title, "Simulated execution" caption on every order ticket and
  proposal-approval button. Driven by `useTenancyStore().mode`.
- **Numeric primitive** with mandatory `tabular-nums` font features so
  rapidly fluctuating prices never reflow surrounding layout.
- **Design tokens** (`src/styles/tokens.css`) — semantic +/-/warn/info
  colours strictly reserved for financial state; brand colours never
  alias into them.
- **CommandK palette**, **AssistantDrawer**, **SandboxBanner**,
  **WorkspaceSwitcher** all wired into the AppShell.

## Routes shipped per phase

- **Phase 0 / 1** — design tokens, throttled WS pipeline, AppShell,
  `/`, `/live`, `/action-center`, `/chat`, kill-switch, sandbox banner.
- **Phase 2 / 2.5** — bots (`/bots`, `/bots/:id`, `/bots/builder`),
  agents (`/agents`, `/agents/registry`, `/agents/runs`,
  `/agents/runs/:id`), backtests (`/backtest`, `/backtest/:id`,
  `/backtest/new`), `/portfolio`, `/paper`, `/monitor`, `/crew`,
  `/ml/training`, `/ml/builder`, `/rl`, `/rl/lab`, `/rl/runs/:id`,
  `/ide`.
- **Phase 3** — `/strategies`, `/strategies/:id`, `/data/catalog`,
  `/data/catalog/:namespace/:name`, `/data/iceberg`, `/data/sources`,
  `/data/sinks`, `/data/indicators`, `/data/kg`,
  `/data/entity-graph`, `/visualizations`, `/rag`, `/rag/admin`,
  `/streaming/kafka`, `/streaming/flink`, `/streaming/producers`.
- **Phase 4** — visual editors: `/workflows/agent`,
  `/workflows/data`, `/workflows/strategy`,
  `/bots/builder`, `/ml/builder`, `/rl/lab`.
- **Phase 5** — admin / tenancy CRUD: `/admin/orgs`, `/admin/teams`,
  `/admin/users`, `/admin/workspaces`, `/admin/projects`,
  `/admin/labs`, `/admin/configs`, `/explorer`, `/models`,
  `/settings`.
- **Phase 6** — specialty: `/options/lab`, `/monte-carlo`,
  `/optimizer`, `/docs`.
- **Phase 7 — Legacy port (B1 – B8)** — the remaining ~60 surfaces
  ported from `webui/` (Agents leaves + hubs + Templates + Evaluations,
  Airbyte workspace, Alpha Vantage dashboard + 11 categories + Admin,
  Data plane: Hub / Explorer / Browser / Symbol Browser / LiveMarket /
  Ingest / Pipelines / Hub / Services / dbt / DataHub / Microstructure /
  Engine / Consolidate / Catalog detail, Regulatory CFPB / FDA / USPTO,
  ML zoo / Models / Datasets / Test, RL zoo / Library / Builders /
  Replay / Runs, Factor / Feature workbench / Taxonomy / Equity
  Research, Streaming detail pages, Strategies/new, real Chat).

## Full route parity

Every nav entry resolves to a real component now. The cover-check is
machine-verified via `frontend/check-coverage.mjs`:

```bash
node check-coverage.mjs
# REAL 86 DYN 42 NAV 86
# MISSING: []
```

The fallback `stubRoute` is a should-never-reach sentinel that logs a
console warning if anybody adds a nav entry without wiring its route.

## Quick start

```bash
# from repo root
cd frontend
pnpm install
pnpm dev   # http://localhost:3001
```

The Vite dev server proxies `/aqp-api/*` -> FastAPI on `:8000` and
`/aqp-ws/*` -> the same target as a WebSocket upgrade. Override with
`VITE_API_URL` / `VITE_WS_URL` in `frontend/.env.local` for direct
connections (Playwright headless against a remote cluster, etc).

The legacy Next.js webui has been **stopped at the cutover** — the
new frontend is now the only operator UI. The `webui` service is left
in `docker-compose.yml` for a one-command rollback
(`docker compose start webui`).

### Docker compose

```bash
# from repo root
docker compose up -d --build frontend   # http://localhost:3002
```

The compose-managed container is published on host **`:3002`** (not
`:3001`) so it can coexist with the dagster-webserver in the
visualization profile, which already binds host `:3001`. The
container itself still listens on `:3001` internally, so
`vite preview` configuration is unchanged.

## Layout

```
frontend/
  src/
    components/
      ui/                 shadcn primitives (Button, Dialog, Tabs, ...)
      common/             Numeric, ConfirmFrictionDialog, KillSwitch,
                          SandboxBanner
      shell/              Sidebar, TopBar, CommandK, WorkspaceSwitcher,
                          AssistantDrawer, AppShell, PageContainer
      charts/             OhlcChart (lightweight-charts), more in
                          phases 2-6
      live/               OrderBook, OrderTicket, PositionTable,
                          WorkingOrders, OrderTape
      action-center/      ProposalCard, ProposalToastBus,
                          ActionCenterPanel, ActionCenterDrawer
      admin/              AdminCrudPage<T> (DataTable + Sheet form +
                          friction-gated delete) used by every
                          /admin/* route
      flow/               WorkflowEditor + Palette + AqpNodeCard
                          used by every /workflows/* and *Builder
                          route
      options/            PayoffChart (D3) for /options/lab
      monte-carlo/        PercentileFan + TerminalHistogram for
                          /monte-carlo
      optimizer/          Heatmap (CSS-grid + d3 colour-scale) for
                          /optimizer
    lib/
      api/                client (openapi-fetch + tenancy middleware),
                          hooks (TanStack Query thin wrappers),
                          query-client, config
      ws/                 client (reconnect + heartbeat), throttle
                          (rAF batcher), useLiveStream, useChatStream,
                          useProposalsStream, types
      utils.ts            cn, formatNumber, formatPercent, formatTime
    routes/               Real route components (dashboard, live,
                          action-center, chat) + stub for unported
                          surfaces
    store/                Zustand: ui, tenancy, market, proposals
    styles/tokens.css     Design tokens
    main.tsx              Entry point
    App.tsx               Provider tree + RouterProvider
    routes.tsx            Route table
  tests/
    unit/                 Vitest (throttle, Numeric, friction dialog,
                          market store)
    e2e/                  Playwright (live + action center smoke)
  Dockerfile
  vite.config.ts
  vitest.config.ts
  playwright.config.ts
  tailwind.config.ts (via tokens.css @import)
  tsconfig.{json,app,node}.json
  biome.json
```

## Hard rules (carry over from AGENTS.md)

- WS payload shape `{task_id, stage, message, timestamp, **extras}` is
  preserved end-to-end. The throttle layer batches but never renames.
- All HTTP requests go through `lib/api/client.ts` — never hand-roll a
  `fetch` so tenancy headers and ApiError normalization stay
  consistent.
- All financial colour signals come from semantic tokens (`--pos-fg`,
  `--neg-fg`, `--warn-fg`, `--info-fg`). Brand / status colours are
  separate; never alias.
- Tabular figures everywhere via the `Numeric` primitive or the
  `.tabular` utility class so numeric columns don't jitter.
- Consequential actions go through `ConfirmFrictionDialog` with a
  typed-confirmation phrase and explicit consequence summary.

## Tests

```bash
pnpm test       # vitest unit suite (throttle, primitives)
pnpm test:e2e   # playwright (boots dev server, runs smoke)
```

`pnpm test:e2e` will start a fresh `pnpm dev` if one is not already
listening on `:3001`. Set `PLAYWRIGHT_NO_SERVER=1` to attach to an
existing server instead.

## Cutover

With Phases 0 – 6 shipped the new frontend is at functional parity
with the legacy `webui/` for everything in scope of the rewrite plan.
Cutover steps are documented in [`CUTOVER.md`](CUTOVER.md). The
remaining stubs are purely the long-tail Research / Service-Manager
niches — see the routes table above.
