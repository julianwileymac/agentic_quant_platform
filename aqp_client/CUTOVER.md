# Frontend cutover plan

The cutover from the legacy Next.js + Antd app at
[`../webui/`](../webui/) to the new Vite + Tailwind + shadcn frontend at
[`./`](.) is **complete as of phase 7**. The legacy webui has been
stopped; the new frontend is the only operator UI.

| Surface | Local dev | docker compose host port | State |
| --- | --- | --- | --- |
| New frontend | `pnpm --dir aqp_client dev` (`:3001`) | `:3002` | active |
| Legacy webui | `pnpm --dir webui dev` (`:3000`) | `:3000` (stopped) | rollback only |

The container internal port is `:3001` for both `vite dev` and `vite preview`;
host port `:3001` is reserved for the dagster-webserver in the
visualization profile, so the compose-managed frontend is published on
`:3002`.

## Pre-cutover checklist (all complete)

- [x] Every nav item in `aqp_client/src/components/shell/nav-config.ts`
      has a corresponding real implementation in `aqp_client/src/routes/`.
      Verified via `node check-coverage.mjs` → `MISSING: []`.
- [x] All Vitest suites pass (`pnpm test` → 48/48).
- [x] Production build succeeds (`pnpm build`).
- [x] Smoke walk of every nav family in headless Chrome — 0 pageerrors.
- [x] `aqp_client/Dockerfile` produces a runnable image
      (`docker compose build frontend`).

## Completed cutover

1. **Legacy webui stopped.** ✓
   ```bash
   docker compose stop webui
   ```

2. *(Optional — pending)* Promote `frontend` to host `:3000`. The
   webui service is left in `aqp_platform/compose/docker-compose.yml` so it can be brought
   back with `docker compose start webui` for a one-command rollback.
   When you're ready to free `:3000`, swap the port mapping:
   ```yaml
   frontend:
     ...
     ports:
       - "3000:3001"      # new app takes :3000
   ```
   At that point the dagster-webserver should also be moved off
   `:3000` if it has been re-bound there in the interim.

5. **Update operator-facing references.**
   - [`../README.md`](../README.md) — point install / dev sections at
     `aqp_client/`.
   - [`../AGENTS.md`](../AGENTS.md) "Where things live" table — change
     the `webui/` entry to `aqp_client/` and add a `webui-legacy/` row.
   - [`../aqp_docs/docs/concepts/platform/architecture.md`](../aqp_docs/docs/concepts/platform/architecture.md) — update the
     UI reference.

6. **Archive the legacy app.**
   Once at least one full release cycle has passed without rolling
   back to the legacy app:
   ```bash
   git mv webui webui-legacy
   git commit -m "chore(webui): archive legacy Next.js app after Vite cutover"
   ```
   The `webui-legacy/` directory remains in the repo so emergency
   rollbacks remain trivial; remove it entirely only after a second
   release cycle.

## Rollback procedure

If a critical regression is found post-cutover:

1. **Restart the legacy webui:**
   ```bash
   docker compose start webui
   ```
   The legacy service is left in `aqp_platform/compose/docker-compose.yml` precisely for this.
2. `docker compose up -d webui frontend`.
3. File a bug, restore the relevant stub in
   `aqp_client/src/routes/<route>/page.tsx` so the legacy app handles
   that route again, redeploy `frontend`, and resume cutover after
   the regression is fixed.

## Hard rules carried over

- **WS payload shape `{task_id, stage, message, timestamp, **extras}`**
  must remain identical end-to-end (AGENTS.md rule 4). The frontend's
  rAF throttler batches but never renames keys.
- **Tenancy headers (`X-AQP-User`, `X-AQP-Workspace`, `X-AQP-Project`,
  `X-AQP-Lab`)** are injected on every fetch by `lib/api/client.ts`.
  Don't hand-roll fetch calls.
- **Semantic financial colours** (`--pos-fg`, `--neg-fg`, `--warn-fg`,
  `--info-fg`) are reserved for financial state. Brand / status colours
  are separate.
