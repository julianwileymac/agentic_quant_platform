import { create } from "zustand";

/**
 * Agent-proposed trade carried over the WS `/agents/proposals/stream`
 * channel. The shape is intentionally permissive — the AgentRuntime
 * may add new fields per-strategy. We narrow only the keys we render.
 */
export interface AgentProposal {
  /** Stable proposal id used for approve / decline endpoints. */
  id: string;
  /** Issuing agent name (e.g. "trader-mean-reversion"). */
  agent: string;
  /** Bot the proposal is associated with, if any. */
  bot_id?: string | null;
  /** vt_symbol the agent wants to trade. */
  vt_symbol: string;
  /** Side (buy / sell). */
  side: "buy" | "sell";
  /** Notional position size (% of NAV) or absolute size. */
  size_pct?: number;
  size_abs?: number;
  /** Limit / market order kind. */
  order_type?: "market" | "limit" | "stop";
  /** Price the agent wants to enter / exit at. */
  price?: number;
  /** Confidence score 0..1. */
  confidence?: number;
  /** Risk metrics carried alongside the proposal. */
  risk?: {
    max_drawdown_pct?: number;
    var_95?: number;
    expected_pnl?: number;
    cost_cap_remaining_usd?: number;
  };
  /** LTL guardrail decisions evaluated by the runtime. */
  guardrails?: Array<{
    id: string;
    rule: string;
    status: "pass" | "warn" | "fail";
    detail?: string;
  }>;
  /** Plain-language rationale from the agent. */
  rationale?: string;
  /** ISO timestamp the proposal was emitted. */
  ts: string;
  /** Status -- 'pending' until approved / declined / expired. */
  status?: "pending" | "approved" | "declined" | "expired" | "executed";
  /** Optional expiry timestamp. */
  expires_at?: string | null;
}

interface ProposalsState {
  pending: AgentProposal[];
  upsert: (proposal: AgentProposal) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export const useProposalsStore = create<ProposalsState>()((set) => ({
  pending: [],
  upsert: (proposal) =>
    set((prev) => {
      const idx = prev.pending.findIndex((p) => p.id === proposal.id);
      if (idx === -1) return { pending: [...prev.pending, proposal] };
      const next = prev.pending.slice();
      next[idx] = { ...next[idx]!, ...proposal };
      return { pending: next };
    }),
  remove: (id) => set((prev) => ({ pending: prev.pending.filter((p) => p.id !== id) })),
  clear: () => set({ pending: [] }),
}));

export function usePendingCount(): number {
  return useProposalsStore((s) => s.pending.filter((p) => (p.status ?? "pending") === "pending").length);
}
