import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { authConfig } from "@/lib/auth/config";
import { consumeFlow, getEntraClient } from "@/lib/auth/entra";
import { buildSession, writeSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";

export const dynamic = "force-dynamic";

interface EntraTenantLinkLookup {
  organization_id: string | null;
  status: "active" | "pending" | "revoked" | "suspended";
}

/**
 * Entra callback: exchange code, resolve `tid` -> EntraTenantLink,
 * write unified session, redirect into the appropriate next step.
 *
 *   active link  -> /dashboard (or returnTo)
 *   pending link -> /onboarding/entra-tenant-link
 *   no link      -> /onboarding/entra-tenant-link?reason=missing
 *
 * AGENTS rule 44: NEVER auto-create an `Organization` from a raw `tid`.
 * The upstream `data.tenancy.link_org_to_entra_tenant` admin step is
 * the only sanctioned ingress; we just route the user to wait.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  if (!code || !state) {
    return NextResponse.json({ error: "missing code or state" }, { status: 400 });
  }
  const flow = consumeFlow(state);
  if (!flow) {
    return NextResponse.json({ error: "unknown or expired state" }, { status: 400 });
  }

  const client = await getEntraClient();
  if (!client) {
    return NextResponse.json({ error: "Entra not configured" }, { status: 503 });
  }

  const result = await client.acquireTokenByCode({
    code,
    scopes: authConfig.entra.scopes,
    redirectUri: authConfig.entra.redirectUri,
    codeVerifier: flow.codeVerifier,
  });

  const idTokenClaims = result.idTokenClaims ?? {};
  const tid = typeof idTokenClaims.tid === "string" ? idTokenClaims.tid : null;
  const oid = typeof idTokenClaims.oid === "string" ? idTokenClaims.oid : null;
  const email =
    typeof idTokenClaims.preferred_username === "string"
      ? idTokenClaims.preferred_username
      : typeof idTokenClaims.email === "string"
        ? idTokenClaims.email
        : "";
  const name = typeof idTokenClaims.name === "string" ? idTokenClaims.name : undefined;
  const user = { id: oid ?? result.account?.homeAccountId ?? "unknown", email, name };

  // AGENTS rule 44: resolve tid -> EntraTenantLink. The upstream route
  // `GET /tenancy/entra-links?tid=...` is the sanctioned read path.
  let nextStep = "/dashboard";
  let enrichedClaims: Record<string, unknown> = idTokenClaims;
  if (tid) {
    try {
      const res = await upstreamFetch(
        `/tenancy/entra-links?tid=${encodeURIComponent(tid)}`,
        {
          session: null,
          headers: { authorization: `Bearer ${result.accessToken}` },
        },
      );
      if (res.ok) {
        const link = (await res.json()) as EntraTenantLinkLookup;
        if (link.status === "active" && link.organization_id) {
          enrichedClaims = {
            ...enrichedClaims,
            [`${authConfig.claimsNamespace}org_id`]: link.organization_id,
          };
          nextStep = flow.returnTo;
        } else {
          nextStep = `/onboarding/entra-tenant-link?status=${link.status}`;
        }
      } else if (res.status === 404) {
        nextStep = "/onboarding/entra-tenant-link?status=missing";
      }
    } catch {
      // Network error contacting upstream — fall through to the
      // waiting screen. The user can retry; we never auto-provision.
      nextStep = "/onboarding/entra-tenant-link?status=unknown";
    }
  }

  const accessTokenExpiresAt = result.expiresOn
    ? Math.floor(result.expiresOn.getTime() / 1000)
    : Math.floor(Date.now() / 1000) + 3600;

  const session = buildSession({
    provider: "entra",
    user,
    rawClaims: enrichedClaims,
    accessToken: result.accessToken,
    accessTokenExpiresAt,
    idToken: result.idToken,
  });
  await writeSession(session);

  return NextResponse.redirect(new URL(nextStep, request.url));
}
