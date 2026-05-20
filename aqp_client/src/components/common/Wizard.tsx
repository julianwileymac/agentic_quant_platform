import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * Generic, headless-with-defaults Wizard / Stepper primitive.
 *
 * Out-of-scope item from the hybrid-agentic-rl-quant plan: lift the
 * common "guided multi-step authoring" pattern out of the individual
 * studios (Alpha Factor, RL Lab, Bot Builder) into a reusable
 * primitive. Plays nicely with `react-hook-form`, but the validator
 * contract is just `() => Promise<boolean> | boolean` so any state
 * library works.
 *
 * Three layers:
 *   1. `<Wizard>` — top-level state + navigation provider.
 *   2. `<WizardStep>` — one step with optional sync/async validator.
 *   3. `useWizard()` — escape hatch for steps that need to query or
 *      mutate the navigation state (e.g. enable Next conditionally).
 *
 * The default chrome (header progress + footer Back/Next/Finish) can
 * be replaced or hidden via the `hideChrome` prop for tightly
 * controlled flows (e.g. inside a dialog).
 */

export interface WizardStepDescriptor {
  /** Unique stable id (used as React key + analytics breadcrumb). */
  id: string;
  /** Short label rendered in the progress strip. */
  title: string;
  /** Optional secondary line under the title. */
  description?: string;
  /**
   * Optional validator fired when the user clicks Next. Return
   * ``false`` (or a rejected promise) to block navigation. The
   * wizard does NOT swallow errors — your validator owns toasts.
   */
  validate?: () => boolean | Promise<boolean>;
  /** Render-prop for the step body. */
  render: (ctx: WizardContextValue) => ReactNode;
  /** Mark a step as optional (renders an "optional" badge). */
  optional?: boolean;
}

export interface WizardContextValue {
  steps: WizardStepDescriptor[];
  current: number;
  /** Move forward (validates current first). */
  next: () => Promise<void>;
  /** Move backward (no validation). */
  back: () => void;
  /** Jump to an arbitrary step. Skips validation entirely. */
  goTo: (index: number) => void;
  /** Mark current step as completed and fire ``onFinish``. */
  finish: () => Promise<void>;
  /** Set of step indices that have already passed their validator. */
  completed: Set<number>;
  /** True while the active validator promise is pending. */
  busy: boolean;
}

interface WizardProps {
  steps: WizardStepDescriptor[];
  /** Fired when the user clicks Finish on the last step (post-validate). */
  onFinish?: () => void | Promise<void>;
  /** Optional title rendered on the Wizard card header. */
  title?: string;
  /** Optional subtitle rendered under the title. */
  subtitle?: string;
  /** Hide the default Card chrome + progress strip + footer. */
  hideChrome?: boolean;
  /** Apply className to the outer container. */
  className?: string;
  /** Initial step index (defaults to 0). */
  initialStep?: number;
}

const WizardContext = createContext<WizardContextValue | undefined>(undefined);

export function Wizard({
  steps,
  onFinish,
  title,
  subtitle,
  hideChrome = false,
  className,
  initialStep = 0,
}: WizardProps) {
  const [current, setCurrent] = useState(
    Math.max(0, Math.min(initialStep, Math.max(0, steps.length - 1))),
  );
  const [completed, setCompleted] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  const runValidator = useCallback(
    async (index: number): Promise<boolean> => {
      const step = steps[index];
      if (!step?.validate) return true;
      setBusy(true);
      try {
        const ok = await Promise.resolve(step.validate());
        return Boolean(ok);
      } finally {
        setBusy(false);
      }
    },
    [steps],
  );

  const goTo = useCallback((index: number) => {
    if (index < 0) return;
    setCurrent(index);
  }, []);

  const back = useCallback(() => {
    setCurrent((c) => Math.max(0, c - 1));
  }, []);

  const next = useCallback(async () => {
    const ok = await runValidator(current);
    if (!ok) return;
    setCompleted((prev) => {
      const nextSet = new Set(prev);
      nextSet.add(current);
      return nextSet;
    });
    setCurrent((c) => Math.min(steps.length - 1, c + 1));
  }, [current, runValidator, steps.length]);

  const finish = useCallback(async () => {
    const ok = await runValidator(current);
    if (!ok) return;
    setCompleted((prev) => {
      const nextSet = new Set(prev);
      nextSet.add(current);
      return nextSet;
    });
    if (onFinish) {
      setBusy(true);
      try {
        await Promise.resolve(onFinish());
      } finally {
        setBusy(false);
      }
    }
  }, [current, onFinish, runValidator]);

  const value = useMemo<WizardContextValue>(
    () => ({ steps, current, next, back, goTo, finish, completed, busy }),
    [steps, current, next, back, goTo, finish, completed, busy],
  );

  const active = steps[current];
  const isLast = current === steps.length - 1;

  const body = active ? active.render(value) : null;

  if (hideChrome) {
    return (
      <WizardContext.Provider value={value}>
        <div className={cn("grid gap-3", className)}>{body}</div>
      </WizardContext.Provider>
    );
  }

  return (
    <WizardContext.Provider value={value}>
      <Card className={cn("flex h-full min-h-0 flex-col", className)}>
        <CardHeader>
          {title ? <CardTitle className="text-sm">{title}</CardTitle> : null}
          {subtitle ? (
            <p className="text-xs text-[var(--text-secondary)]">{subtitle}</p>
          ) : null}
          <WizardProgress />
        </CardHeader>
        <CardContent className="flex h-full min-h-0 flex-col gap-3">
          <div className="min-h-0 flex-1 overflow-auto">{body}</div>
          <WizardFooter isLast={isLast} />
        </CardContent>
      </Card>
    </WizardContext.Provider>
  );
}

function WizardProgress() {
  const ctx = useWizard();
  return (
    <ol className="mt-2 flex flex-wrap items-stretch gap-2">
      {ctx.steps.map((step, i) => {
        const isActive = i === ctx.current;
        const isComplete = ctx.completed.has(i);
        return (
          <li key={step.id} className="flex items-stretch gap-2">
            <button
              type="button"
              onClick={() => ctx.goTo(i)}
              className={cn(
                "flex items-center gap-2 rounded-md border px-2 py-1 text-left text-xs transition-colors",
                isActive
                  ? "border-[var(--info-fg)] bg-[var(--info-bg)] text-[var(--info-fg)]"
                  : isComplete
                    ? "border-[var(--pos-fg)] text-[var(--pos-fg)]"
                    : "border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]",
              )}
              aria-current={isActive ? "step" : undefined}
            >
              <span
                className={cn(
                  "grid h-5 w-5 place-items-center rounded-full border text-[10px] font-semibold",
                  isActive
                    ? "border-[var(--info-fg)] bg-[var(--info-fg)] text-[var(--info-bg)]"
                    : isComplete
                      ? "border-[var(--pos-fg)] bg-[var(--pos-fg)] text-[var(--bg-app)]"
                      : "border-[var(--border-default)]",
                )}
              >
                {isComplete ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              <span>
                <span className="block font-medium">{step.title}</span>
                {step.description ? (
                  <span className="block text-[10px] opacity-70">
                    {step.description}
                  </span>
                ) : null}
              </span>
              {step.optional ? (
                <Badge variant="outline" className="ml-1 text-[9px]">
                  optional
                </Badge>
              ) : null}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function WizardFooter({ isLast }: { isLast: boolean }) {
  const ctx = useWizard();
  return (
    <div className="flex items-center justify-between gap-2 border-t border-[var(--border-default)] pt-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={ctx.back}
        disabled={ctx.current === 0 || ctx.busy}
        className="gap-1"
      >
        <ChevronLeft className="h-3 w-3" /> Back
      </Button>
      <span className="text-[10px] text-[var(--text-secondary)]">
        Step {ctx.current + 1} of {ctx.steps.length}
      </span>
      {isLast ? (
        <Button
          type="button"
          size="sm"
          onClick={ctx.finish}
          disabled={ctx.busy}
          className="gap-1"
        >
          {ctx.busy ? "Working..." : "Finish"} <Check className="h-3 w-3" />
        </Button>
      ) : (
        <Button
          type="button"
          size="sm"
          onClick={ctx.next}
          disabled={ctx.busy}
          className="gap-1"
        >
          {ctx.busy ? "Validating..." : "Next"}{" "}
          <ChevronRight className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
}

/**
 * Optional helper component for steps. Equivalent to inlining the
 * render-prop body, but renders consistent spacing + sub-headers.
 */
export function WizardStep({
  title,
  description,
  children,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-3">
      {title ? <h4 className="text-sm font-medium">{title}</h4> : null}
      {description ? (
        <p className="text-xs text-[var(--text-secondary)]">{description}</p>
      ) : null}
      {children}
    </div>
  );
}

export function useWizard(): WizardContextValue {
  const ctx = useContext(WizardContext);
  if (!ctx) {
    throw new Error("useWizard must be used inside <Wizard />");
  }
  return ctx;
}
