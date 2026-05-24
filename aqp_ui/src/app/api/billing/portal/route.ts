import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";

export const dynamic = "force-dynamic";

/**
 * Stripe Customer Portal handoff.
 *
 * AGENTS rule 4: never log the returned portal URL or any token in it.
 */
export async function POST(): Promise<NextResponse> {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const upstream = await upstreamFetch("/billing/portal", {
    method: "POST",
    base: "control_plane",
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
