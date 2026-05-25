/**
 * Confirmation dialog that requires the operator to type a phrase
 * verbatim before the destructive action fires.
 *
 * Mirrors the aqp_client ConfirmFrictionDialog conventions
 * (frontend.mdc) so the muscle memory transfers between operator
 * surfaces. Headless / Tailwind-only — no Radix dep here.
 */
import type { ReactNode } from "react";
import { useState } from "react";

import { cn } from "@/lib/cn";

export type ConfirmFrictionDialogProps = {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmPhrase: string;
  destructive?: boolean;
  busy?: boolean;
  onCancel(): void;
  onConfirm(reason: string): void;
};

export function ConfirmFrictionDialog({
  open,
  title,
  description,
  confirmPhrase,
  destructive = true,
  busy = false,
  onCancel,
  onConfirm,
}: ConfirmFrictionDialogProps) {
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  const matches = typed.trim() === confirmPhrase;
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl border bg-white p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-semibold">{title}</h2>
        <div className="mb-4 text-sm text-slate-600">{description}</div>
        <label className="mb-2 block text-xs font-medium text-slate-500">
          Type <code className="font-mono">{confirmPhrase}</code> to confirm.
        </label>
        <input
          className="mb-3 w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-500"
          autoFocus
          autoComplete="off"
          value={typed}
          placeholder={confirmPhrase}
          onChange={(e) => setTyped(e.target.value)}
        />
        <label className="mb-2 block text-xs font-medium text-slate-500">
          Optional reason (recorded in the audit ledger).
        </label>
        <input
          className="mb-4 w-full rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-500"
          autoComplete="off"
          value={reason}
          placeholder="kill-switch"
          onChange={(e) => setReason(e.target.value)}
        />
        <div className="flex justify-end gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-slate-100 disabled:opacity-50"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!matches || busy}
            className={cn(
              "rounded-md px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50",
              destructive ? "bg-red-600 hover:bg-red-700" : "bg-slate-900 hover:bg-slate-700",
            )}
            onClick={() => onConfirm(reason || "kill-switch")}
          >
            {busy ? "Working..." : destructive ? "Confirm destructive action" : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}
