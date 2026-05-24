# aqp-admin-ui

Vite 7 + React 19 + Tailwind 4 + shadcn-style admin frontend for
[aqp_admin](../README.md).

## Dev

```bash
pnpm install
pnpm dev        # http://localhost:3003 (proxies /admin/* -> :8900)
pnpm typecheck
pnpm test
pnpm build
```

## Layout

```
src/
├── main.tsx                 # bootstrap (QueryClient, Router, App)
├── App.tsx                  # route shell
├── components/layout/AdminShell.tsx
├── routes/
│   ├── dashboard.tsx
│   ├── accounts.tsx
│   └── services.tsx
├── lib/
│   ├── api.ts               # typed admin API wrappers
│   └── cn.ts                # className merger
└── styles/index.css         # Tailwind 4 + design tokens
```

Mirrors [aqp_client](../../aqp_client/)'s conventions (port `3001`,
biome lint, vitest, pnpm); this app uses port `3003` and the
`/admin/*` API surface.
