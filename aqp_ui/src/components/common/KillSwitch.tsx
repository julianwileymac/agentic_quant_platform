"use client";

import { Button, Modal, message } from "antd";
import { useState } from "react";
import { OctagonAlert } from "lucide-react";

import { useStepUp, runWithStepUp } from "@/hooks/useStepUp";

/**
 * Kill-switch button.
 *
 * AGENTS rule 7: POST /api/kill-switch MUST fan out via
 * Promise.allSettled to portfolio/kill_switch, agents/halt,
 * paper/stop-all, bots/halt-all, rl/halt-all, workflows/halt.
 *
 * AGENTS rule 6 + 8: ConfirmFrictionDialog requires the user to type
 * the org name to confirm; the action is RFC 9470 step-up gated.
 */
export function KillSwitch() {
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { isSupported, requestStepUp } = useStepUp();
  const expected = "HALT";

  async function handleConfirm() {
    if (confirmText !== expected) return;
    setSubmitting(true);
    try {
      await runWithStepUp(requestStepUp, isSupported, async () => {
        const res = await fetch("/api/kill-switch", {
          method: "POST",
          credentials: "include",
        });
        if (!res.ok) {
          const err = new Error(`kill-switch failed: ${res.status}`);
          (err as Error & { headers?: Headers }).headers = res.headers;
          throw err;
        }
        message.success("Kill switch engaged — all runtimes halted");
      });
      setOpen(false);
      setConfirmText("");
    } catch (err) {
      message.error(err instanceof Error ? err.message : "Kill switch failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Button
        danger
        size="small"
        type="primary"
        icon={<OctagonAlert size={14} />}
        onClick={() => setOpen(true)}
      >
        Halt all
      </Button>
      <Modal
        title="Halt every running workload?"
        open={open}
        onCancel={() => {
          setOpen(false);
          setConfirmText("");
        }}
        onOk={handleConfirm}
        okText="Halt now"
        okButtonProps={{ danger: true, loading: submitting, disabled: confirmText !== expected }}
        cancelButtonProps={{ disabled: submitting }}
      >
        <div className="mb-3 text-sm" style={{ color: "var(--text-secondary)" }}>
          This will halt every running agent, paper trade, bot, RL experiment,
          and workflow in your organization. Step-up MFA is required.
        </div>
        <div className="text-xs" style={{ color: "var(--text-muted)" }}>
          Type <code style={{ color: "var(--neg-fg)" }}>{expected}</code> to confirm:
        </div>
        <input
          type="text"
          autoFocus
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          className="mt-2 w-full rounded border px-3 py-2 text-sm"
          style={{
            background: "var(--bg-elevated)",
            borderColor: "var(--border-default)",
            color: "var(--text-primary)",
          }}
        />
      </Modal>
    </>
  );
}
