import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * Health check used by Kubernetes liveness + readiness probes.
 *
 * Deliberately does NOT call upstream services — that would couple our
 * pod readiness to backend availability and prevent the marketing site
 * from being reachable during a backend outage. For a deeper health
 * check that includes upstream connectivity, see `/api/healthz/deep`
 * (sprint 7).
 */
export async function GET(): Promise<NextResponse> {
  return NextResponse.json(
    {
      service: "aqp-ui",
      version: process.env.NEXT_PUBLIC_AQP_UI_VERSION ?? "0.1.0",
      env: process.env.NODE_ENV,
      ts: new Date().toISOString(),
      status: "ok",
    },
    { status: 200, headers: { "cache-control": "no-store" } },
  );
}
