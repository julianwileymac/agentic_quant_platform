import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";
import { bubbleStepUp } from "@/lib/auth/stepUp";

export const dynamic = "force-dynamic";

/**
 * Strategies list (read) + create (write).
 *
 * AGENTS rule 6: bubble step-up challenges on write paths.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const search = request.nextUrl.searchParams.toString();
  const upstream = await upstreamFetch(`/strategies${search ? `?${search}` : ""}`);
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const upstream = await upstreamFetch("/strategies", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: await request.text(),
  });

  const response = new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
  return bubbleStepUp(upstream, response);
}
