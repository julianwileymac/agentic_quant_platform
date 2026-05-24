import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/session";
import { upstreamFetch } from "@/lib/api/client";
import { bubbleStepUp } from "@/lib/auth/stepUp";

export const dynamic = "force-dynamic";

const HALT_ENDPOINTS = [
  "/portfolio/kill_switch",
  "/agents/halt",
  "/paper/stop-all",
  "/bots/halt-all",
  "/rl/halt-all",
  "/workflows/halt",
] as const;

interface HaltResult {
  endpoint: string;
  status: number;
  ok: boolean;
  error?: string;
}

/**
 * Halt every running runtime across the user's tenant.
 *
 * AGENTS rule 7: fans out via Promise.allSettled. Any 401 with an
 * RFC 9470 step-up challenge is bubbled back unchanged so the client
 * can prompt for fresh MFA and retry.
 *
 * AGENTS rule 11: re-check session here even though middleware ran.
 */
export async function POST(): Promise<NextResponse> {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const settled = await Promise.allSettled(
    HALT_ENDPOINTS.map(async (endpoint): Promise<HaltResult> => {
      try {
        const res = await upstreamFetch(endpoint, { method: "POST" });
        if (res.status === 401) {
          // Surface the step-up challenge as a first-class result so
          // the orchestrator below can preserve the WWW-Authenticate.
          const wwwAuth = res.headers.get("www-authenticate") ?? "";
          if (/insufficient_user_authentication/.test(wwwAuth)) {
            const err = new Error("step_up_required");
            (err as Error & { upstreamResponse?: Response }).upstreamResponse = res;
            throw err;
          }
        }
        return { endpoint, status: res.status, ok: res.ok };
      } catch (err) {
        return {
          endpoint,
          status: 0,
          ok: false,
          error: err instanceof Error ? err.message : String(err),
        };
      }
    }),
  );

  const results: HaltResult[] = settled.map((r, i) => {
    const fallback: HaltResult = {
      endpoint: HALT_ENDPOINTS[i] ?? "",
      status: 0,
      ok: false,
      error: "task_rejected",
    };
    return r.status === "fulfilled" ? r.value : fallback;
  });

  // If any endpoint reported a step-up challenge, bubble its
  // WWW-Authenticate header so the client can prompt for MFA.
  const stepUp = settled.find(
    (r) =>
      r.status === "rejected" &&
      (r.reason as Error)?.message === "step_up_required",
  );
  if (stepUp && stepUp.status === "rejected") {
    const upstream = (
      stepUp.reason as Error & { upstreamResponse?: Response }
    ).upstreamResponse;
    const body = NextResponse.json(
      { error: "step_up_required", results },
      { status: 401 },
    );
    if (upstream) return bubbleStepUp(upstream, body);
    return body;
  }

  const allOk = results.every((r) => r.ok);
  return NextResponse.json(
    { ok: allOk, results },
    { status: allOk ? 200 : 207 },
  );
}
