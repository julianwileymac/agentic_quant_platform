# Auth0 + React SPA (2026) Best Practices

For a Vite 7 + React 19 SPA, the current stable pattern with `@auth0/auth0-react` is:

1. initialize once with `Auth0Provider`,
2. use `loginWithRedirect` for session creation with explicit API `audience`/`scope`,
3. acquire backend tokens on demand via `getAccessTokenSilently`,
4. protect route-level UI with `withAuthenticationRequired`,
5. choose token cache mode deliberately (`memory` vs `localstorage`) based on security posture.

This keeps authentication concerns predictable while still supporting enterprise API authorization from the browser.

## 1) Provider setup and callback handling in Vite

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { Auth0Provider } from "@auth0/auth0-react";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <Auth0Provider
    domain={import.meta.env.VITE_AUTH0_DOMAIN}
    clientId={import.meta.env.VITE_AUTH0_CLIENT_ID}
    authorizationParams={{
      redirect_uri: `${window.location.origin}/auth/callback`,
      audience: "https://api.your-company.com",
      scope: "openid profile email read:positions write:orders",
    }}
    useRefreshTokens
    cacheLocation="memory"
  >
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </Auth0Provider>,
);
```

In Vite, keep callback origins aligned with Auth0 allowed callback/logout/web-origin settings for each environment (`localhost`, staging, prod).

## 2) `useAuth0()` vs `withAuthenticationRequired`

- `useAuth0()` is your low-level SDK hook (login/logout, token fetch, user state, loading state).
- `withAuthenticationRequired` is best for route/component guards that should auto-redirect unauthenticated users.

Use both: hook for behavior, HOC for route protection.

```tsx
import { withAuthenticationRequired } from "@auth0/auth0-react";

function PositionsPage() {
  return <div>Positions</div>;
}

export default withAuthenticationRequired(PositionsPage, {
  onRedirecting: () => <div>Redirecting to login...</div>,
});
```

## 3) Silent token refresh and storage trade-offs

`getAccessTokenSilently` is the primary browser API-token path.

With `useRefreshTokens={true}` and offline access allowed, the SDK prefers refresh-token based renewal. Without that, browser silent auth may rely on hidden iframe behavior that is more sensitive to cookie/browser policies.

### Storage choice
- `memory` (recommended default): strongest XSS posture, but tokens are not persisted across full page reloads/tabs.
- `localstorage`: better UX persistence and fewer reauth frictions, but larger XSS blast radius if the app is compromised.

For trading platforms, many teams keep memory cache in production and only move to `localstorage` when UX constraints force it, alongside aggressive XSS hardening (CSP, dependency hygiene, no unsafe eval).

## 4) Requesting API access correctly

Always request the API audience/scope either at login or token fetch time; then pass Bearer tokens to FastAPI.

```tsx
import { useAuth0 } from "@auth0/auth0-react";

export function useOrdersApi() {
  const { getAccessTokenSilently } = useAuth0();

  async function listOrders() {
    const accessToken = await getAccessTokenSilently({
      authorizationParams: {
        audience: "https://api.your-company.com",
        scope: "read:orders",
      },
    });

    const res = await fetch("https://api.your-company.com/orders", {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  }

  return { listOrders };
}
```

## 5) Operational guidance for 2026 rollouts

- Keep login and API token params consistent (same `audience`, required scopes).
- Treat token acquisition failures as recoverable UX states (retry, then redirect).
- Instrument auth metrics: token fetch failure rate, redirect loops, callback errors, session expiration behavior.
- Run browser matrix tests (Chrome, Safari, Edge) specifically for silent refresh behavior.
- Keep Auth0 package versions pinned and upgrade via staged canaries.

---

## Sources

- https://auth0.com/docs/quickstart/spa/react
- https://github.com/auth0/auth0-react
- https://github.com/auth0/auth0-react/blob/master/EXAMPLES.md
- https://auth0.com/docs/authenticate/login/configure-silent-authentication
- https://auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation
- https://vite.dev/guide/
