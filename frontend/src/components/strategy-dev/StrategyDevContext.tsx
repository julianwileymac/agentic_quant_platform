import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

/**
 * Cross-route persistent state for the consolidated `/strategy-development/*`
 * umbrella. Selections (deployment, symbols, time window, feature row,
 * run id, composed YAML) survive navigation between sibling sub-routes so
 * researchers don't have to re-enter context when switching between
 * predict-batch, compare-models, scenario-perturbation, etc.
 *
 * Backed purely by React state plus localStorage persistence. The reason
 * we don't use the URL is so deeply nested complex objects (feature
 * rows, multi-perturbation grids) stay clean in the address bar.
 */

export interface StrategyDevSelection {
  deploymentId: string;
  /** Optional second deployment for A/B compare flows. */
  deploymentIdB?: string;
  symbols: string[];
  start: string;
  end: string;
  /** JSON-serialised feature row used by single + scenario sub-routes. */
  featureRowText: string;
  perturbations: number[];
  /** Last launched task id surfaced into the KPI strip. */
  lastTaskId?: string | null;
  /** Last completed run summary, for the persistent KPI strip. */
  lastRunSummary?: RunSummary | null;
  /** Strategy id being authored / iterated on in the composer. */
  strategyId?: string | null;
  /** Free-form YAML being composed before save-to-library. */
  composerYaml?: string;
  /**
   * Phase B (agentic-RL UI studios): symbolic alpha factor being
   * authored in the Alpha Factor Studio. Persisted so navigating
   * to the Gallery and clicking "Use as template" -> back doesn't
   * lose work.
   */
  alphaFormula?: string;
  alphaFormulaName?: string;
  alphaRationale?: string;
  /**
   * Recent alpha proposals (most-recent first). The studio's
   * "Recent" library tab reads this so the user can quickly pull
   * back a formula they were just iterating on.
   */
  recentAlphas?: Array<{
    name: string;
    formula: string;
    rationale?: string;
    savedAt: string;
  }>;
  /**
   * Gallery selection deep-link state — when set, the gallery sets
   * this before navigating to a studio, and the studio reads +
   * clears it on mount. Avoids relying purely on URL query params
   * when the payload is large.
   */
  gallerySelection?: {
    kind: "alpha_factor" | "rl_spec" | "agent_spec";
    slug: string;
    payload?: Record<string, unknown>;
  } | null;
}

export interface RunSummary {
  runId: string;
  kind: "backtest" | "paper" | "lob" | "alpha_backtest" | "rl" | "ml_test";
  sharpe?: number | null;
  totalReturn?: number | null;
  maxDrawdown?: number | null;
  hitRate?: number | null;
  trades?: number | null;
  /** Free-form key->value tail metrics (winrate, expectancy, etc). */
  extras?: Record<string, number | string | null>;
  /** Wall-clock timestamp the snapshot was emitted. */
  at?: string;
}

interface StrategyDevContextValue {
  selection: StrategyDevSelection;
  setSelection: (patch: Partial<StrategyDevSelection>) => void;
  resetSelection: () => void;
}

const STORAGE_KEY = "aqp.strategy-dev.selection.v1";

const INITIAL: StrategyDevSelection = {
  deploymentId: "",
  symbols: ["AAPL", "MSFT"],
  start: "2024-01-01",
  end: "2024-06-30",
  featureRowText: '{"feature_a": 0.5, "feature_b": -0.2}',
  perturbations: [-0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2],
  lastTaskId: null,
  lastRunSummary: null,
  strategyId: null,
  composerYaml: "",
  alphaFormula: "",
  alphaFormulaName: "",
  alphaRationale: "",
  recentAlphas: [],
  gallerySelection: null,
};

const StrategyDevContext = createContext<StrategyDevContextValue | undefined>(undefined);

function loadInitial(): StrategyDevSelection {
  if (typeof window === "undefined") return INITIAL;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return INITIAL;
    const parsed = JSON.parse(raw) as Partial<StrategyDevSelection>;
    return { ...INITIAL, ...parsed };
  } catch {
    return INITIAL;
  }
}

export function StrategyDevProvider({ children }: { children: ReactNode }) {
  const [selection, setSelectionState] = useState<StrategyDevSelection>(loadInitial);

  const setSelection = useCallback(
    (patch: Partial<StrategyDevSelection>) => {
      setSelectionState((prev) => {
        const next = { ...prev, ...patch };
        if (typeof window !== "undefined") {
          try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
          } catch {
            /* quota; ignore */
          }
        }
        return next;
      });
    },
    [],
  );

  const resetSelection = useCallback(() => {
    setSelectionState(INITIAL);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
    }
  }, []);

  const value = useMemo<StrategyDevContextValue>(
    () => ({ selection, setSelection, resetSelection }),
    [selection, setSelection, resetSelection],
  );

  return <StrategyDevContext.Provider value={value}>{children}</StrategyDevContext.Provider>;
}

export function useStrategyDev(): StrategyDevContextValue {
  const ctx = useContext(StrategyDevContext);
  if (!ctx) {
    throw new Error("useStrategyDev must be used inside <StrategyDevProvider />");
  }
  return ctx;
}
