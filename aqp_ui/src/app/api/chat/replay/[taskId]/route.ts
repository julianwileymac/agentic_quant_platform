import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";

export const dynamic = "force-dynamic";

interface RouteParams {
  params: Promise<{ taskId: string }>;
}

/**
 * Phase 3 (WS replay) — proxy to upstream
 * `GET /chat/replay/{task_id}?since=&limit=`.
 *
 * Used by [`useCeleryTask`](../../../../hooks/useCeleryTask.ts) on
 * every WebSocket reconnect to fill the gap between the last frame
 * the client saw and the next live frame. The upstream emits frames
 * in canonical
 * `{task_id, stage, message, timestamp, frame_id, **extras}` shape.
 *
 * AGENTS rule 4: frame shape contract is preserved unchanged — we
 * only add `frame_id` for replay bookkeeping. AGENTS rule 11: the
 * BFF re-checks the session even though middleware ran.
 */
export async function GET(
  request: NextRequest,
  { params }: RouteParams,
): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { taskId } = await params;
  const search = request.nextUrl.searchParams.toString();
  const upstream = await upstreamFetch(
    `/chat/replay/${encodeURIComponent(taskId)}${search ? `?${search}` : ""}`,
  );
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type":
        upstream.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}
