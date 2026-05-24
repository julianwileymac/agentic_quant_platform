import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

/**
 * Returns the non-sensitive subset of the unified session to the
 * client (provider, user metadata, namespaced claims). The raw access
 * token is NEVER returned — clients call BFF endpoints, which inject
 * the token server-side.
 *
 * AGENTS rule 4 + aqp-management-engine.mdc: no tokens in response body.
 */
export async function GET(): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json(
      { user: null, claims: null, provider: null },
      { status: 200, headers: { "cache-control": "no-store" } },
    );
  }
  return NextResponse.json(
    {
      user: session.user,
      claims: session.claims,
      provider: session.provider,
    },
    { status: 200, headers: { "cache-control": "no-store" } },
  );
}
