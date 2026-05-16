import {
  Beaker,
  BookOpen,
  Boxes,
  FileSearch,
  Gauge,
  LineChart,
  Library,
  PlayCircle,
  Radar,
  Sparkles,
  Wand2,
  type LucideIcon,
} from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

export interface StrategyDevSubRoute {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
  group: "Author" | "Test" | "Knowledge";
}

export const STRATEGY_DEV_ROUTES: StrategyDevSubRoute[] = [
  {
    to: "/strategy-development/composer",
    label: "Composer",
    description: "Drag-drop palette + YAML editor",
    icon: Boxes,
    group: "Author",
  },
  {
    to: "/strategy-development/simulation",
    label: "Simulation",
    description: "Unified backtest / paper / RL launcher",
    icon: PlayCircle,
    group: "Author",
  },
  {
    to: "/strategy-development/ideation",
    label: "Ideation",
    description: "LLM-driven strategy ideation",
    icon: Sparkles,
    group: "Author",
  },
  {
    to: "/strategy-development/single-predict",
    label: "Single Predict",
    description: "One-row inference against a deployment",
    icon: Wand2,
    group: "Test",
  },
  {
    to: "/strategy-development/predict-batch",
    label: "Predict Batch",
    description: "Iceberg slice scoring (or DuckDB bars)",
    icon: LineChart,
    group: "Test",
  },
  {
    to: "/strategy-development/compare-models",
    label: "Compare Models",
    description: "A/B compare two deployments",
    icon: Gauge,
    group: "Test",
  },
  {
    to: "/strategy-development/scenario-perturbation",
    label: "Scenario / What-if",
    description: "Sensitivity ladder + stress test",
    icon: Radar,
    group: "Test",
  },
  {
    to: "/strategy-development/historical-eval",
    label: "Historical",
    description: "Walk-forward / split-plan evaluation",
    icon: Beaker,
    group: "Test",
  },
  {
    to: "/strategy-development/live-test",
    label: "Live Test",
    description: "Stream predictions on live data",
    icon: PlayCircle,
    group: "Test",
  },
  {
    to: "/strategy-development/document-library",
    label: "Document Library",
    description: "Math-aware research-paper browser",
    icon: BookOpen,
    group: "Knowledge",
  },
  {
    to: "/strategy-development/library",
    label: "Strategy Library",
    description: "Registered strategies + components",
    icon: Library,
    group: "Knowledge",
  },
  {
    to: "/strategy-development/run-comparator",
    label: "Run Comparator",
    description: "Compare N runs (Sharpe, DD, P&L)",
    icon: FileSearch,
    group: "Test",
  },
];

const GROUP_ORDER: StrategyDevSubRoute["group"][] = ["Author", "Test", "Knowledge"];

export function StrategyDevSubNav() {
  return (
    <nav
      aria-label="Strategy development tools"
      className="flex w-[220px] shrink-0 flex-col gap-3 border-r border-[var(--border-default)] bg-[var(--bg-surface)] p-3 text-xs"
    >
      {GROUP_ORDER.map((group) => {
        const items = STRATEGY_DEV_ROUTES.filter((r) => r.group === group);
        if (!items.length) return null;
        return (
          <div key={group} className="flex flex-col gap-1">
            <div className="px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">
              {group}
            </div>
            <ul className="flex flex-col gap-px">
              {items.map((it) => (
                <li key={it.to}>
                  <NavLink
                    to={it.to}
                    end={false}
                    className={({ isActive }) =>
                      cn(
                        "flex items-start gap-2 rounded-md px-2 py-1.5 text-[var(--text-secondary)] transition-colors",
                        "hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]",
                        isActive && "bg-[var(--info-bg)] text-[var(--info-fg)]",
                      )
                    }
                  >
                    <it.icon className="mt-px h-3.5 w-3.5 shrink-0" />
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[12px] font-medium">{it.label}</span>
                      <span className="text-[10px] leading-tight opacity-70">
                        {it.description}
                      </span>
                    </div>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}
