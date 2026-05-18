# Auth0 + Next.js 15 App Router (2026) Best Practices

For legacy production webui on Next.js 15, `@auth0/nextjs-auth0` v4 should be treated as the canonical integration path. The practical operating model is:

1. one shared server-side `Auth0Client` instance,
2. middleware-based route/session handling,
3. server-first session/token access in App Router,
4. optional client provider only when client-side auth state is explicitly needed.

This keeps the auth boundary clean while your Vite frontend becomes primary.

## 1) Shared `Auth0Client` singleton

Create one reusable instance (for Server Components, route handlers, and server actions):

```ts
// src/lib/auth0.ts
import { Auth0Client } from "@auth0/nextjs-auth0/server";

export const auth0 = new Auth0Client({
  domain: process.env.AUTH0_DOMAIN!,
  clientId: process.env.AUTH0_CLIENT_ID!,
  clientSecret: process.env.AUTH0_CLIENT_SECRET!,
  secret: process.env.AUTH0_SECRET!,
  appBaseUrl: process.env.APP_BASE_URL!,
  authorizationParameters: {
    audience: "https://api.your-company.com",
    scope: "openid profile email read:positions write:orders",
  },
});
```

Keep this server-only. Do not recreate per request.

## 2) `middleware.ts` matcher strategy

In v4, middleware is central to session/auth route handling and protects selected surfaces.

```ts
// middleware.ts
import { auth0 } from "./src/lib/auth0";
import type { NextRequest } from "next/server";

export async function middleware(request: NextRequest) {
  return auth0.middleware(request);
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
```

Protecting everything then explicitly excluding static assets is usually the least fragile pattern in production.

## 3) Server Components: `getSession()` and `getAccessToken()`

In App Router, prefer server-side retrieval:

```ts
// app/(secure)/positions/page.tsx
import { redirect } from "next/navigation";
import { auth0 } from "@/lib/auth0";

export default async function PositionsPage() {
  const session = await auth0.getSession();
  if (!session) redirect("/auth/login");

  const { accessToken } = await auth0.getAccessToken();
  const res = await fetch("https://api.your-company.com/positions", {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });

  const data = await res.json();
  return <pre>{JSON.stringify(data, null, 2)}</pre>;
}
```

This avoids leaking token logic into browser JS and gives predictable SSR behavior.

## 4) Built-in auth routes and flow

Default route set includes:
- `/auth/login`
- `/auth/logout`
- `/auth/callback`

These routes should be in your Auth0 app URL allowlists (callback/logout), and they are enough for most deployments without custom handlers.

## 5) When to add client `<Auth0Provider>`

In Next.js App Router, a client provider is optional.

Use it only when you need interactive client-side auth state (for example, optimistic nav bars or user menu hydration patterns that must react without full server round-trips). If most auth-aware rendering is server-first, skip provider complexity and use `getSession()` in Server Components/layouts.

## 6) v3 -> v4 migration notes to account for

Common migration tasks:
- environment naming updates (`APP_BASE_URL`, `AUTH0_DOMAIN` style config),
- route assumptions changed to `/auth/*`,
- middleware/proxy setup becomes mandatory for normal operation,
- verify audience/scope flow with `getAccessToken()` in App Router contexts.

Run a migration checklist against:
- callback URL correctness,
- logout URL correctness,
- middleware matcher behavior,
- server component token fetch behavior,
- API authorization headers to FastAPI.

---

## Sources

- https://github.com/auth0/nextjs-auth0
- https://github.com/auth0/nextjs-auth0/blob/main/V4_MIGRATION_GUIDE.md
- https://auth0.github.io/nextjs-auth0/
- https://auth0.com/docs/quickstart/webapp/nextjs
- https://nextjs.org/docs/app/building-your-application/routing/middleware
