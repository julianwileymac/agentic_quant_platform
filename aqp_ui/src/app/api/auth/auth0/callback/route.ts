import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { decodeJwt } from "jose";

import { authConfig } from "@/lib/auth/config";
import { buildSession, writeSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

/**
 * Auth0 callback: exchanges the authorization code for tokens,
 * builds the unified session, writes the JWE cookie, redirects.
 *
 * The Auth0 v4 SDK normally owns this round trip via the catch-all
 * `/auth/[...auth0]` handler. We implement an explicit version so:
 *   (a) Both Auth0 and Entra share an identical callback shape.
 *   (b) Local dev (and the Auth0-disabled fallback) still works.
 *
 * AGENTS rule 4: we NEVER log the access token. The whole token blob
 * is encrypted into the session cookie immediately.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!authConfig.auth0.enabled) {
    return NextResponse.json({ error: "Auth0 disabled" }, { status: 400 });
  }
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!code) {
    return NextResponse.json({ error: "missing code" }, { status: 400 });
  }

  // Exchange the auth code for tokens. AGENTS rule 4 + the always-on
  // management-engine rule forbid printing tokens; we keep them in
  // local scope and seal them into the JWE cookie immediately.
  const tokenRes = await fetch(`https://${authConfig.auth0.domain}/oauth/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      grant_type: "authorization_code",
      client_id: authConfig.auth0.clientId,
      client_secret: authConfig.auth0.clientSecret,
      code,
      redirect_uri: `${authConfig.appBaseUrl}/api/auth/auth0/callback`,
    }),
  });

  if (!tokenRes.ok) {
    return NextResponse.json(
      { error: "token_exchange_failed", status: tokenRes.status },
      { status: 502 },
    );
  }

  const tokens = (await tokenRes.json()) as {
    access_token: string;
    id_token?: string;
    refresh_token?: string;
    expires_in?: number;
    token_type?: string;
  };

  let claims: Record<string, unknown> = {};
  let user = { id: "unknown", email: "" } as {
    id: string;
    email: string;
    name?: string;
    picture?: string;
  };
  if (tokens.id_token) {
    try {
      claims = decodeJwt(tokens.id_token) as Record<string, unknown>;
      user = {
        id: String(claims.sub ?? "unknown"),
        email: String(claims.email ?? ""),
        name: typeof claims.name === "string" ? claims.name : undefined,
        picture: typeof claims.picture === "string" ? claims.picture : undefined,
      };
    } catch {
      // Malformed id_token — fall through to /auth/error.
    }
  }

  const session = buildSession({
    provider: "auth0",
    user,
    rawClaims: claims,
    accessToken: tokens.access_token,
    accessTokenExpiresAt:
      Math.floor(Date.now() / 1000) + (tokens.expires_in ?? 3600),
    refreshToken: tokens.refresh_token,
    idToken: tokens.id_token,
  });
  await writeSession(session);

  // Resolve returnTo from a state cookie or query param (the
  // Auth0 SDK keeps it for us; the manual path falls back to /dashboard).
  const stateReturnTo = state ? decodeURIComponent(state) : null;
  const returnTo =
    request.nextUrl.searchParams.get("returnTo") ?? stateReturnTo ?? "/dashboard";

  return NextResponse.redirect(new URL(returnTo, request.url));
}
