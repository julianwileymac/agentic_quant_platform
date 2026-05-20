import { AlertTriangle, ShieldAlert } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface RiskLine {
  label: string;
  value: ReactNode;
  /** Optional tone hint that maps to a +/- color. */
  tone?: "positive" | "negative" | "warn" | "neutral";
}

interface ConfirmFrictionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Headline shown in the dialog (e.g. "Halt all running agents?"). */
  title: string;
  /** Plain-language consequence summary. */
  consequence: string;
  /**
   * Bullet list of trade / risk parameters the user must read before
   * confirming. Rendered as a description list with semantic colours.
   */
  details?: RiskLine[];
  /**
   * If supplied, the user must type this exact phrase before the action
   * is enabled. Defaults to "CONFIRM" for irreversible actions; pass
   * empty string to disable typed-confirmation friction.
   */
  confirmPhrase?: string;
  /** Label for the confirm button. */
  confirmLabel?: string;
  /** Variant of the confirm button. */
  confirmVariant?: "destructive" | "warn" | "default";
  /** Async action; resolves when complete. Errors propagate via toast. */
  onConfirm: () => void | Promise<void>;
  /** Optional extra body content rendered above the typed-confirmation gate. */
  children?: ReactNode;
}

/**
 * Purposeful-friction dialog used by every consequential action across
 * the AQP frontend (kill-switch, agent-proposed trade approval, manual
 * order tickets, paper-mode toggles, irreversible config writes).
 *
 * The blueprint mandates "intentionally slow the user down" before any
 * irreversible action. We achieve that with three layers of friction:
 *   1. An explicit consequence summary in plain language.
 *   2. A description list of the actual trade / risk parameters with
 *      semantic +/- colour coding for fast visual parsing.
 *   3. A typed-confirmation gate ("type CONFIRM to proceed") that
 *      demands the user reads the dialog before the action enables.
 *
 * The confirm button is always destructive- or warn-variant (red /
 * amber) and never the same colour as routine "Save" actions, so the
 * user is physiologically aware they are about to do something
 * non-routine.
 */
export function ConfirmFrictionDialog({
  open,
  onOpenChange,
  title,
  consequence,
  details = [],
  confirmPhrase = "CONFIRM",
  confirmLabel = "Confirm",
  confirmVariant = "destructive",
  onConfirm,
  children,
}: ConfirmFrictionDialogProps) {
  const [typed, setTyped] = useState("");
  const [isSubmitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      setTyped("");
      setSubmitting(false);
    }
  }, [open]);

  const requiresPhrase = confirmPhrase.length > 0;
  const phraseSatisfied = !requiresPhrase || typed.trim() === confirmPhrase;

  const handleConfirm = async () => {
    if (!phraseSatisfied || isSubmitting) return;
    setSubmitting(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setSubmitting(false);
    }
  };

  const variantToColor =
    confirmVariant === "destructive"
      ? "bg-[var(--neg-fg)] hover:bg-[var(--neg-fg)]/90"
      : confirmVariant === "warn"
        ? "bg-[var(--warn-fg)] hover:bg-[var(--warn-fg)]/90 text-black"
        : "bg-[var(--info-fg)] hover:bg-[var(--info-fg)]/90";

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <div className="flex items-center gap-2 text-[var(--warn-fg)]">
            {confirmVariant === "destructive" ? (
              <ShieldAlert className="h-5 w-5" />
            ) : (
              <AlertTriangle className="h-5 w-5" />
            )}
            <AlertDialogTitle>{title}</AlertDialogTitle>
          </div>
          <AlertDialogDescription>{consequence}</AlertDialogDescription>
        </AlertDialogHeader>

        {details.length > 0 ? (
          <dl className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3">
            {details.map((line, idx) => (
              <div
                key={`${line.label}-${idx}`}
                className="flex items-start justify-between gap-3 py-1 text-sm"
              >
                <dt className="text-[var(--text-secondary)]">{line.label}</dt>
                <dd
                  className="font-mono"
                  style={{
                    fontVariantNumeric: "tabular-nums",
                    color:
                      line.tone === "positive"
                        ? "var(--pos-fg)"
                        : line.tone === "negative"
                          ? "var(--neg-fg)"
                          : line.tone === "warn"
                            ? "var(--warn-fg)"
                            : "var(--text-primary)",
                  }}
                >
                  {line.value}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}

        {children}

        {requiresPhrase ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="confirm-friction-phrase">
              Type <span className="font-mono text-[var(--warn-fg)]">{confirmPhrase}</span> to enable
            </Label>
            <Input
              id="confirm-friction-phrase"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              autoFocus
              placeholder={confirmPhrase}
              className="font-mono"
            />
          </div>
        ) : null}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isSubmitting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={!phraseSatisfied || isSubmitting}
            onClick={(e) => {
              e.preventDefault();
              void handleConfirm();
            }}
            className={variantToColor}
          >
            {isSubmitting ? "Working…" : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
