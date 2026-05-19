# Research index

This directory stores external research snapshots used to guide architectural
changes. Treat these files as **time-bound guidance**, not canonical runtime
contracts.

## Source of truth priority

1. `AGENTS.md` + `.cursor/rules/*.mdc`
2. `docs/architecture/decisions/*.md`
3. `docs/operations/*.md`
4. `.cursor/research/*.md` (this folder)

If research findings conflict with architecture decisions or hard rules, follow
the architecture decisions and hard rules.

## Current files

| File | Topic | Source window | Status |
| --- | --- | --- | --- |
| `auth0-2026-fastapi-best-practices.md` | FastAPI/Auth0 patterns | 2026-05 | advisory |
| `auth0-2026-nextjs15-app-router-best-practices.md` | Next.js/Auth0 patterns | 2026-05 | advisory |
| `auth0-2026-react-spa-best-practices.md` | SPA/Auth0 patterns | 2026-05 | advisory |
| `auth0-2026-signup-account-management-ux.md` | account UX patterns | 2026-05 | advisory |
| `auth0-2026-entra-federation-through-auth0.md` | Entra/Auth0 federation patterns | 2026-05 | advisory |

## Refresh policy

- Refresh research when a major dependency or platform shifts (Auth0 SDK major,
  FastAPI major, Kubernetes baseline, or deployment model).
- Record the query intent and date inside each research file.
- Do not store secrets or tenant identifiers in research snapshots.

## Tavily usage

Use Tavily (`tvly research ...`) for deep research updates, then run a docs
reliability pass before promoting findings into canonical docs.
