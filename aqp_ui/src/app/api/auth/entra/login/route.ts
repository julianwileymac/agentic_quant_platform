import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { randomBytes } from "node:crypto";

import { authConfig } from "@/lib/auth/config";
import { generatePkce, getEntraClient, rememberFlow } from "@/lib/auth/entra";

export const dynamic = "force-dynamic";

/**
 * Entra login entrypoint — server-side MSAL PKCE flow.
 *
 * Multi-tenant by default (authority = login.microsoftonline.com/common).
 * On callback we resolve the `tid` claim against the existing
 * `entra_tenant_links` table per AGENTS rule 44.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!authConfig.entra.enabled) {
    return NextResponse.json({ error: "Entra disabled" }, { status: 400 });
  }
  const client = await getEntraClient();
  if (!client) {
    return NextResponse.json(
      { error: "Entra not configured" },
      { status: 503 },
    );
  }

  const returnTo = request.nextUrl.searchParams.get("returnTo") ?? "/dashboard";
  const loginHint = request.nextUrl.searchParams.get("login_hint") ?? undefined;

  const state = randomBytes(16).toString("base64url");
  const { codeVerifier, codeChallenge } = await generatePkce();
  rememberFlow(state, codeVerifier, returnTo);

  const url = await client.getAuthCodeUrl({
    scopes: authConfig.entra.scopes,
    redirectUri: authConfig.entra.redirectUri,
    state,
    codeChallenge,
    codeChallengeMethod: "S256",
    loginHint,
  });
  return NextResponse.redirect(url);
}
