# AGENTS.md

Agent contract for `aqp_client`.

## Purpose

This boundary owns the local user-facing client: the Vite operator UI,
typed API access, client-side session state, visualization surfaces, and
alert subscriptions.

## Hard Boundaries

1. Use the API wrappers in `aqp_client/src/lib/api/`; do not hand-roll
   unaudited `fetch` calls.
2. Keep tenancy, auth, error normalization, and generated OpenAPI types in
   the shared client layer.
3. Consequential actions must use existing friction patterns and preserve the
   kill-switch fan-out contract.
4. WebSocket frames keep `{task_id, stage, message, timestamp, **extras}`.
5. Do not add backend business logic or direct persistence access here.

## Where Changes Go

- Active route/component changes: `src/routes/` or `src/components/`.
- Typed API wrappers: `src/lib/api/`.
- Client boundary documentation: this folder.
- Backend route behavior: `../aqp/api/routes/` or `../aqp_control_plane/`.

## Validation

```bash
pnpm --dir aqp_client typecheck
pnpm --dir aqp_client test
pnpm --dir aqp_client build
```

