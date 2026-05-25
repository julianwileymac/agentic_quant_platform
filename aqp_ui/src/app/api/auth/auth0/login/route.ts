import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { authConfig } from "@/lib/auth/config";
import { getAuth0Client } from "@/lib/auth/auth0";

export const dynamic = "force-dynamic";

/**
 * Auth0 login entrypoint.
 *
 * Delegates to `@auth0/nextjs-auth0` v4 client.startInteractiveLogin
 * when available. Falls back to a hand-built Universal Login URL so
 * that local dev without the Auth0 SDK can still complete the round
 * trip against a deployed AQP backend.
 *
 * AGENTS rule 2: this handler is the ONLY place where `getAuth0Client`
 * is invoked from outside `src/lib/auth/auth0.ts`.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!authConfig.auth0.enabled) {
    return NextResponse.json({ error: "Auth0 disabled" }, { status: 400 });
  }
  const search = request.nextUrl.searchParams;
  const screenHint = search.get("screen_hint") ?? undefined;
  const returnTo = search.get("returnTo") ?? "/dashboard";
  const organization = search.get("organization") ?? undefined;

  const client = await getAuth0Client();
  if (!client) {
    return NextResponse.json(
      { error: "Auth0 not configured" },
      { status: 503 },
    );
  }

  const sdk = client as unknown as {
    startInteractiveLogin?: (req: {
      returnTo?: string;
      authorizationParameters?: Record<string, string>;
    }) => Promise<Response>;
  };

  if (typeof sdk.startInteractiveLogin === "function") {
    const params: Record<string, string> = {};
    if (screenHint) params.screen_hint = screenHint;
    if (organization) params.organization = organization;
    const upstream = await sdk.startInteractiveLogin({
      returnTo,
      authorizationParameters: params,
    });
    // The SDK returns a Response whose Location header points at
    // Auth0's /authorize. App-router handlers can't return
    // NextResponse.next() (that's a middleware-only call), so we
    // extract the upstream Location + Set-Cookie headers and emit a
    // proper 302 from the route.
    const location = upstream.headers.get("location");
    if (location) {
      const redirect = NextResponse.redirect(location, { status: 302 });
      for (const cookie of upstream.headers.getSetCookie?.() ?? []) {
        redirect.headers.append("set-cookie", cookie);
      }
      return redirect;
    }
    // SDK didn't produce a Location — fall through to the manual
    // Universal Login URL below.
  }

  const url = new URL(`https://${authConfig.auth0.domain}/authorize`);
  url.searchParams.set("client_id", authConfig.auth0.clientId);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("redirect_uri", `${authConfig.appBaseUrl}/api/auth/auth0/callback`);
  url.searchParams.set("scope", authConfig.auth0.scope);
  url.searchParams.set("audience", authConfig.auth0.audience);
  if (screenHint) url.searchParams.set("screen_hint", screenHint);
  if (organization) url.searchParams.set("organization", organization);
  return NextResponse.redirect(url);
}
