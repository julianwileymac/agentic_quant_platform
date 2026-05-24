import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const upstream = await upstreamFetch("/tenancy/members");
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
