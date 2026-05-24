import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { SignJWT } from "jose";

import { getSession } from "@/lib/auth/session";
import { authConfig } from "@/lib/auth/config";
import { tenancyQueryParams } from "@/lib/api/tenancy";

export const dynamic = "force-dynamic";

const TICKET_TTL_SECONDS = 60;

/**
 * Mint a short-lived WebSocket ticket bound to (user, tenant, channel).
 *
 * Returns the upstream WSS URL with the ticket attached. The ticket is
 * a signed JWT (HS256) using AQP_UI_SESSION_SECRET as the shared key —
 * the upstream gateway validates with the same key. TTL of 60s prevents
 * replay; the ticket can be reused once per channel.
 *
 * AGENTS rule 4: NEVER include the user's full access token in the URL.
 * AGENTS rule 6: tenant_id binding rejects cross-tenant subscription.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const params = request.nextUrl.searchParams;
  const taskId = params.get("taskId");
  const channelId = params.get("channelId");
  if (!taskId && !channelId) {
    return NextResponse.json(
      { error: "missing taskId or channelId" },
      { status: 400 },
    );
  }

  const now = Math.floor(Date.now() / 1000);
  const key = new TextEncoder().encode(authConfig.session.secret || "dev-secret");
  const claim = {
    sub: session.user.id,
    org: session.claims.orgId ?? "",
    workspace: session.claims.workspaceId ?? "",
    ...(taskId ? { task_id: taskId } : {}),
    ...(channelId ? { channel_id: channelId } : {}),
    iat: now,
    exp: now + TICKET_TTL_SECONDS,
  };
  const ticket = await new SignJWT(claim)
    .setProtectedHeader({ alg: "HS256" })
    .sign(key);

  const path = taskId
    ? `/chat/stream/${encodeURIComponent(taskId)}`
    : `/live/stream/${encodeURIComponent(channelId!)}`;

  const url = new URL(path, authConfig.upstream.wsBase);
  url.searchParams.set("ticket", ticket);
  for (const [k, v] of Object.entries(tenancyQueryParams(session))) {
    url.searchParams.set(k, v);
  }

  return NextResponse.json(
    { wsUrl: url.toString(), expiresIn: TICKET_TTL_SECONDS },
    { headers: { "cache-control": "no-store" } },
  );
}
