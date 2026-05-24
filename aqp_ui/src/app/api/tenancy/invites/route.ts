import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";
import { bubbleStepUp } from "@/lib/auth/stepUp";

export const dynamic = "force-dynamic";

export async function GET(): Promise<NextResponse> {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const upstream = await upstreamFetch("/tenancy/invites");
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export async function POST(request: Request): Promise<NextResponse> {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const upstream = await upstreamFetch("/tenancy/invites", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await request.text(),
  });
  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
  return bubbleStepUp(upstream, response);
}
