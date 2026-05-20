/**
 * Typed client for the Phase 5 ``GET /agents/health`` route.
 *
 * Read-only — the matching mutating action (halt) is the existing
 * ``POST /agents/halt`` already wired through the topbar kill-switch
 * (see ``aqp_client/src/components/common/KillSwitch.tsx``).
 */
import { apiFetch } from "@/lib/api/client";

export type StalledCandidate = {
  run_id: string;
  spec: string;
  started_at: string;
  task_id: string | null;
  stalled_seconds: number;
  status: "running" | "pending";
};

export type AgentHealthResponse = {
  running: number;
  pending: number;
  halted_last_24h: number;
  stalled_candidates: StalledCandidate[];
  stall_threshold_seconds: number;
  last_watchdog_at: string;
};

export async function getAgentHealth(): Promise<AgentHealthResponse> {
  return apiFetch("/agents/health");
}
