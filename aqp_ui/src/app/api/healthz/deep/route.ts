import { NextResponse } from "next/server";

import { authConfig } from "@/lib/auth/config";

export const dynamic = "force-dynamic";

/**
 * Deep health check.
 *
 * Probes upstream API connectivity via a HEAD against /readyz (no auth
 * required). NOT wired into Kubernetes liveness/readiness probes — the
 * shallow /api/healthz is. This endpoint exists for SRE dashboards and
 * synthetic monitoring (Pingdom / Grafana / etc).
 *
 * AGENTS rule 4: never print or return tokens or other secret material.
 */
export async function GET(): Promise<NextResponse> {
  const checks: Record<string, { ok: boolean; status?: number; error?: string }> = {};

  await Promise.all([
    probe(checks, "api", `${authConfig.upstream.apiBase}/readyz`),
    probe(checks, "control_plane", `${authConfig.upstream.controlPlaneBase}/manage/readyz`),
  ]);

  const allOk = Object.values(checks).every((c) => c.ok);
  return NextResponse.json(
    {
      service: "aqp-ui",
      checks,
      ts: new Date().toISOString(),
      status: allOk ? "ok" : "degraded",
    },
    { status: allOk ? 200 : 503, headers: { "cache-control": "no-store" } },
  );
}

async function probe(
  out: Record<string, { ok: boolean; status?: number; error?: string }>,
  key: string,
  url: string,
): Promise<void> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(url, { method: "HEAD", signal: controller.signal });
    clearTimeout(timer);
    out[key] = { ok: res.ok, status: res.status };
  } catch (err) {
    out[key] = { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}
