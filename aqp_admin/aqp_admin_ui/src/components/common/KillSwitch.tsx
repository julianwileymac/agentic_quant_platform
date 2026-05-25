/**
 * Kill-switch — fan-out halt button mounted in the admin shell topbar.
 *
 * Hits the brokered ``POST /admin/halt/all`` endpoint which fans out
 * to every CP + monolith halt URL in parallel. Friction-gated via
 * :class:`ConfirmFrictionDialog` (the operator must type the
 * confirm phrase verbatim).
 */
import { useState } from "react";

import { adminApi, type HaltAllResponse } from "@/lib/api";

import { ConfirmFrictionDialog } from "./ConfirmFrictionDialog";

const CONFIRM_PHRASE = "halt";

export function KillSwitch() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState<HaltAllResponse | null>(null);

  async function fire(reason: string) {
    setBusy(true);
    try {
      const result = await adminApi.haltAll(reason);
      setLastResult(result);
    } catch (err) {
      console.error("kill-switch fan-out failed", err);
    } finally {
      setBusy(false);
      setOpen(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      {lastResult ? (
        <span className="text-xs text-slate-500">
          last halt: {lastResult.halted.length} succeeded, {lastResult.failures.length} failed
        </span>
      ) : null}
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 rounded-md border border-red-300 bg-red-50 px-3 py-1.5 text-sm font-semibold text-red-700 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-500"
        title="Kill-switch — halts every long-running runtime"
      >
        <span aria-hidden>STOP</span>
        <span>Kill switch</span>
      </button>
      <ConfirmFrictionDialog
        open={open}
        title="Engage the kill-switch?"
        description={
          <>
            This fans out a halt to every long-running runtime — agents, paper
            sessions, bots, RL, workflows, the control-plane WorkloadRuntime,
            and the Terraform IaC runtime. In-flight runs cooperatively
            cancel and write a <code>status=halted</code> audit row.
          </>
        }
        confirmPhrase={CONFIRM_PHRASE}
        destructive
        busy={busy}
        onCancel={() => setOpen(false)}
        onConfirm={(reason) => void fire(reason)}
      />
    </div>
  );
}
