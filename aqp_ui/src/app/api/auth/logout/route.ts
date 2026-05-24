import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { authConfig } from "@/lib/auth/config";
import { clearSession, getSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

/**
 * Provider-agnostic logout.
 *
 * 1. Clear the unified JWE session cookie.
 * 2. Redirect to the active provider's RP-Initiated Logout endpoint
 *    (Auth0 /v2/logout or Entra /common/oauth2/v2.0/logout) when an
 *    upstream session is still attached. Falls back to the homepage
 *    if neither is configured.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  return doLogout(request);
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  return doLogout(request);
}

async function doLogout(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  await clearSession();

  const returnTo =
    request.nextUrl.searchParams.get("returnTo") ?? authConfig.appBaseUrl;

  if (session?.provider === "auth0" && authConfig.auth0.domain) {
    const url = new URL(`https://${authConfig.auth0.domain}/v2/logout`);
    url.searchParams.set("client_id", authConfig.auth0.clientId);
    url.searchParams.set("returnTo", returnTo);
    return NextResponse.redirect(url);
  }
  if (session?.provider === "entra") {
    const url = new URL(`${authConfig.entra.authority}/oauth2/v2.0/logout`);
    url.searchParams.set("post_logout_redirect_uri", returnTo);
    return NextResponse.redirect(url);
  }
  return NextResponse.redirect(returnTo);
}
