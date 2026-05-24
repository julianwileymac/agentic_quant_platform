import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { authConfig } from "@/lib/auth/config";
import { getSession } from "@/lib/auth/session";
import { ACR_MFA } from "@/lib/auth/stepUp";

export const dynamic = "force-dynamic";

/**
 * Step-up endpoint that the client popup hits to request a fresh MFA
 * assertion from the active identity provider.
 *
 * Auth0:  /authorize with acr_values + max_age=0 + prompt=login.
 * Entra:  /authorize with claims={"id_token":{"acr":{"essential":true,"value":"mfa"}}} + max_age=0.
 *
 * The popup completes the round-trip with the IdP and closes itself.
 * The next call from the client retries automatically (apiFetch).
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    const url = new URL("/login", request.url);
    return NextResponse.redirect(url);
  }
  const acrValues = request.nextUrl.searchParams.get("acr_values") ?? ACR_MFA;
  const maxAge = request.nextUrl.searchParams.get("max_age") ?? "0";

  if (session.provider === "auth0" && authConfig.auth0.domain) {
    const url = new URL(`https://${authConfig.auth0.domain}/authorize`);
    url.searchParams.set("client_id", authConfig.auth0.clientId);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("redirect_uri", `${authConfig.appBaseUrl}/api/auth/auth0/callback`);
    url.searchParams.set("scope", authConfig.auth0.scope);
    url.searchParams.set("audience", authConfig.auth0.audience);
    url.searchParams.set("acr_values", acrValues);
    url.searchParams.set("max_age", maxAge);
    url.searchParams.set("prompt", "login");
    return NextResponse.redirect(url);
  }

  if (session.provider === "entra") {
    const url = new URL(`${authConfig.entra.authority}/oauth2/v2.0/authorize`);
    url.searchParams.set("client_id", authConfig.entra.clientId);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("redirect_uri", authConfig.entra.redirectUri);
    url.searchParams.set("response_mode", "query");
    url.searchParams.set("scope", authConfig.entra.scopes.join(" "));
    url.searchParams.set("max_age", maxAge);
    url.searchParams.set(
      "claims",
      JSON.stringify({
        id_token: { acr: { essential: true, value: "mfa" } },
      }),
    );
    return NextResponse.redirect(url);
  }

  return NextResponse.json({ error: "no upstream provider" }, { status: 400 });
}
