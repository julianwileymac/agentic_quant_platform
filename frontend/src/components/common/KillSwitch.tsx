import { Power } from "lucide-react";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { Button } from "@/components/ui/button";
import { toast } from "@/components/ui/toast";
import { apiFetch } from "@/lib/api/client";

/**
 * Halt endpoints fanned out in parallel. The backend treats each as
 * idempotent (404 means "nothing to stop") so a single failure on one
 * subsystem doesn't block the others.
 *
 * ``/quant-agents/halt`` is a narrow companion to ``/agents/halt`` —
 * it halts only the LLM-driven quant agents (alpha_researcher +
 * strategy_executor) introduced by the hybrid agentic-RL rollout.
 * It runs in addition to ``/agents/halt`` (which already covers it)
 * because the spec-narrow endpoint surfaces explicit telemetry in
 * the aggregate toast — operators want to confirm the quant cohort
 * actually got terminated rather than infer it from a count.
 *
 * ``rl_trading`` bots (Phase 8) inherit halt semantics from
 * ``/bots/halt-all`` (bot deployment halt) AND ``/rl/halt-all``
 * (the underlying RL training loop); both are in the list already
 * so no per-kind entry is required.
 */
const HALT_ENDPOINTS: ReadonlyArray<{ path: string; label: string }> = [
  { path: "/agents/halt", label: "spec-driven agent runs (all cohorts)" },
  { path: "/quant-agents/halt", label: "quant agents (alpha_researcher + strategy_executor)" },
  { path: "/paper/stop-all", label: "paper trading sessions" },
  { path: "/bots/halt-all", label: "live bot deployments (incl. rl_trading)" },
  { path: "/rl/halt-all", label: "RL train / paper / replay runs" },
];

/**
 * Global kill-switch surfaced in the TopBar. Clicking opens a friction
 * dialog summarising every subsystem about to be halted; the user must
 * type CONFIRM to proceed.
 *
 * On submit we POST to all halt endpoints in parallel and surface a
 * single aggregate toast — partial failures are still surfaced but
 * never block the rest.
 */
export function KillSwitch() {
  const [open, setOpen] = useState(false);
  const [isHalting, setHalting] = useState(false);

  const onConfirm = async () => {
    setHalting(true);
    try {
      const results = await Promise.allSettled(
        HALT_ENDPOINTS.map(({ path }) => apiFetch(path, { method: "POST" })),
      );
      const failed = results
        .map((r, i) => ({ r, i }))
        .filter(({ r }) => r.status === "rejected");
      if (failed.length === 0) {
        toast.success("All subsystems halted", {
          description: "Agents, paper, bots, and RL stopped successfully.",
        });
      } else {
        toast.warning("Halt completed with partial failures", {
          description: failed
            .map(({ i }) => HALT_ENDPOINTS[i]?.label ?? "unknown subsystem")
            .join(", "),
        });
      }
    } finally {
      setHalting(false);
    }
  };

  return (
    <>
      <Button
        variant="destructive"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={isHalting}
        className="gap-2 font-semibold uppercase tracking-wide"
        aria-label="Kill switch — halt all running agents, bots, and paper sessions"
      >
        <Power className="h-4 w-4" />
        Halt
      </Button>
      <ConfirmFrictionDialog
        open={open}
        onOpenChange={setOpen}
        title="Halt every running subsystem"
        consequence="This stops every running agent (including alpha_researcher + strategy_executor), paper session, RL run, and live-bot deployment (including rl_trading bots) immediately. In-flight orders may still settle. This cannot be reversed without a manual restart."
        details={HALT_ENDPOINTS.map((e) => ({
          label: e.label,
          value: e.path,
          tone: "warn",
        }))}
        confirmPhrase="HALT"
        confirmLabel="Halt all subsystems"
        confirmVariant="destructive"
        onConfirm={onConfirm}
      />
    </>
  );
}
