import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";

export interface BuildSpec {
  class: string;
  module_path: string;
  kwargs: Record<string, unknown>;
}

export interface WeightCentricSelection {
  selector: BuildSpec | null;
  allocator: BuildSpec | null;
  timing: BuildSpec | null;
  risk_overlay: BuildSpec | null;
}

interface Props {
  value: WeightCentricSelection;
  onChange: (value: WeightCentricSelection) => void;
  /** Symbols available for the StaticUniverseSelector. */
  symbols?: string[];
}

/**
 * Phase B panel for the FinRL-X four-stage portfolio pipeline
 * (`f_S -> f_A -> f_T -> f_R`). Emits a per-stage build-spec dict;
 * the runtime composes them inside `WeightCentricPipeline`.
 *
 * The panel hard-wires the known concrete classes (per
 * `aqp/rl/portfolio/__init__.py`) so users don't have to remember
 * module paths. For the long-tail "custom selector" use case, drive
 * the canvas in `/rl/lab` directly.
 */
const SELECTOR_OPTIONS = [
  {
    alias: "StaticUniverseSelector",
    module: "aqp.rl.portfolio.selector",
    label: "Static universe (passthrough)",
  },
  {
    alias: "LiquiditySelector",
    module: "aqp.rl.portfolio.selector",
    label: "Liquidity filter (min ADV)",
  },
];

const ALLOCATOR_OPTIONS = [
  {
    alias: "IdentityAllocator",
    module: "aqp.rl.portfolio.allocator",
    label: "Identity (raw RL action)",
  },
  {
    alias: "SoftmaxAllocator",
    module: "aqp.rl.portfolio.allocator",
    label: "Softmax (long-only simplex)",
  },
];

const TIMING_OPTIONS = [
  {
    alias: "ConstantTimingAdjuster",
    module: "aqp.rl.portfolio.timing",
    label: "Constant (no scaling)",
  },
  {
    alias: "TurbulenceTimingAdjuster",
    module: "aqp.rl.portfolio.timing",
    label: "Turbulence regime gating",
  },
  {
    alias: "VolatilityTargetingTimingAdjuster",
    module: "aqp.rl.portfolio.timing",
    label: "Vol targeting",
  },
];

const RISK_OPTIONS = [
  {
    alias: "PositionCapRiskOverlay",
    module: "aqp.rl.portfolio.risk_overlay",
    label: "Position cap only",
  },
  {
    alias: "GrossExposureRiskOverlay",
    module: "aqp.rl.portfolio.risk_overlay",
    label: "Gross exposure cap only",
  },
  {
    alias: "StackedRiskOverlay",
    module: "aqp.rl.portfolio.risk_overlay",
    label: "Stacked (cap + gross)",
  },
];

export function WeightCentricPipelinePanel({ value, onChange, symbols = [] }: Props) {
  const [selector, setSelector] = useState<BuildSpec | null>(value.selector);
  const [allocator, setAllocator] = useState<BuildSpec | null>(value.allocator);
  const [timing, setTiming] = useState<BuildSpec | null>(value.timing);
  const [riskOverlay, setRiskOverlay] = useState<BuildSpec | null>(value.risk_overlay);

  useEffect(() => {
    onChange({ selector, allocator, timing, risk_overlay: riskOverlay });
  }, [selector, allocator, timing, riskOverlay, onChange]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          Weight-centric pipeline
          <Badge variant="secondary">f_S -&gt; f_A -&gt; f_T -&gt; f_R</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <p className="text-xs text-[var(--text-secondary)]">
          The FinRL-X four-stage protocol. Same target weight vector flows
          through the offline backtest and the live broker; the only
          difference is the venue.
        </p>
        <StageSelect
          stageLabel="f_S — Selector"
          options={SELECTOR_OPTIONS}
          value={selector}
          onChange={(alias, module) =>
            setSelector(
              alias
                ? {
                    class: alias,
                    module_path: module,
                    kwargs:
                      alias === "StaticUniverseSelector"
                        ? { universe: symbols }
                        : alias === "LiquiditySelector"
                          ? { min_dollar_volume: 1_000_000 }
                          : {},
                  }
                : null,
            )
          }
        />
        <StageSelect
          stageLabel="f_A — Allocator"
          options={ALLOCATOR_OPTIONS}
          value={allocator}
          onChange={(alias, module) =>
            setAllocator(
              alias
                ? {
                    class: alias,
                    module_path: module,
                    kwargs:
                      alias === "SoftmaxAllocator" ? { temperature: 1.0 } : {},
                  }
                : null,
            )
          }
        />
        <StageSelect
          stageLabel="f_T — Timing"
          options={TIMING_OPTIONS}
          value={timing}
          onChange={(alias, module) =>
            setTiming(
              alias
                ? {
                    class: alias,
                    module_path: module,
                    kwargs:
                      alias === "TurbulenceTimingAdjuster"
                        ? { threshold: 140.0, cooldown_scale: 0.0 }
                        : alias === "VolatilityTargetingTimingAdjuster"
                          ? { target_vol: 0.1, max_scale: 2.0 }
                          : {},
                  }
                : null,
            )
          }
        />
        <StageSelect
          stageLabel="f_R — Risk overlay"
          options={RISK_OPTIONS}
          value={riskOverlay}
          onChange={(alias, module) =>
            setRiskOverlay(
              alias
                ? {
                    class: alias,
                    module_path: module,
                    kwargs:
                      alias === "PositionCapRiskOverlay"
                        ? { max_position_pct: 0.3, mark_truncated: true }
                        : alias === "GrossExposureRiskOverlay"
                          ? { max_gross: 1.0 }
                          : alias === "StackedRiskOverlay"
                            ? {
                                overlays: [
                                  {
                                    class: "PositionCapRiskOverlay",
                                    module_path: "aqp.rl.portfolio.risk_overlay",
                                    kwargs: { max_position_pct: 0.3, mark_truncated: true },
                                  },
                                  {
                                    class: "GrossExposureRiskOverlay",
                                    module_path: "aqp.rl.portfolio.risk_overlay",
                                    kwargs: { max_gross: 1.0 },
                                  },
                                ],
                              }
                            : {},
                  }
                : null,
            )
          }
        />
      </CardContent>
    </Card>
  );
}

interface StageSelectProps {
  stageLabel: string;
  options: ReadonlyArray<{ alias: string; module: string; label: string }>;
  value: BuildSpec | null;
  onChange: (alias: string | null, module: string) => void;
}

function StageSelect({ stageLabel, options, value, onChange }: StageSelectProps) {
  const moduleByAlias = Object.fromEntries(options.map((o) => [o.alias, o.module]));
  const current = value?.class ?? "";
  return (
    <div className="grid gap-1">
      <Label htmlFor={`stage-${stageLabel}`}>{stageLabel}</Label>
      <select
        id={`stage-${stageLabel}`}
        value={current}
        onChange={(e) => {
          const v = e.target.value || null;
          onChange(v, v ? (moduleByAlias[v] ?? "") : "");
        }}
        className="h-9 rounded-md border border-[var(--border-default)] bg-transparent px-2 font-mono text-sm"
      >
        <option value="">— pick —</option>
        {options.map((o) => (
          <option key={o.alias} value={o.alias}>
            {o.label}
          </option>
        ))}
      </select>
      {value ? (
        <details>
          <summary className="cursor-pointer text-[10px] text-[var(--text-secondary)]">
            kwargs preview
          </summary>
          <pre className="overflow-auto rounded bg-[var(--bg-elevated)] p-2 text-[10px]">
            {JSON.stringify(value.kwargs, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
