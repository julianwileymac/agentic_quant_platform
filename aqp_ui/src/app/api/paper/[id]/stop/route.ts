import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";
import { bubbleStepUp } from "@/lib/auth/stepUp";

export const dynamic = "force-dynamic";

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function POST(_req: Request, { params }: RouteParams) {
  const session = await getSession();
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const { id } = await params;
  const upstream = await upstreamFetch(`/paper/${encodeURIComponent(id)}/stop`, {
    method: "POST",
  });
  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
  return bubbleStepUp(upstream, response);
}
