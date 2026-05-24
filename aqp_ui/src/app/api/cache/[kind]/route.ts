import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";

export const dynamic = "force-dynamic";

interface CacheCategoryParams {
  params: Promise<{ kind: string }>;
}

/**
 * Thin proxy to the upstream metadata cache (`GET /cache/{kind}`).
 *
 * Backs the EntityPicker (AGENTS rule 8). Strict whitelist of categories
 * lives in the upstream (`aqp.cache.keys.CACHE_CATEGORIES`); the BFF
 * forwards arbitrary `kind` values and lets the upstream reject
 * unknown ones with 404.
 */
export async function GET(
  request: NextRequest,
  { params }: CacheCategoryParams,
): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { kind } = await params;
  const search = request.nextUrl.searchParams;
  const upstream = await upstreamFetch(`/cache/${encodeURIComponent(kind)}?${search.toString()}`);

  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "content-type":
        upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}
