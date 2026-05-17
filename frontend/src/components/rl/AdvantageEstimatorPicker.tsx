import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRegistryComponent, useRegistryKind } from "@/lib/api/registry";

export interface AdvantageSelection {
  alias: string;
  module_path: string;
  kwargs: Record<string, unknown>;
}

interface Props {
  value: AdvantageSelection | null;
  onChange: (value: AdvantageSelection | null) => void;
}

/**
 * Phase B picker for the Phase 2 `rl_advantage_estimator`
 * registrations (ReinforcePlusPlus / GRPO / GAE). Emits a build-spec
 * dict that the `RLExperimentSpec.training.advantage` field accepts
 * directly.
 */
export function AdvantageEstimatorPicker({ value, onChange }: Props) {
  const list = useRegistryKind("rl_advantage_estimator");
  const [alias, setAlias] = useState<string | null>(value?.alias ?? null);
  const detail = useRegistryComponent(
    alias ? "rl_advantage_estimator" : null,
    alias ?? null,
  );
  const [kwargs, setKwargs] = useState<Record<string, unknown>>(value?.kwargs ?? {});

  useEffect(() => {
    if (!alias || !detail.data) {
      onChange(null);
      return;
    }
    const moduleParts = detail.data.qualname.split(".");
    moduleParts.pop();
    const modulePath = detail.data.module ?? moduleParts.join(".");
    onChange({
      alias,
      module_path: modulePath,
      kwargs,
    });
  }, [alias, detail.data, kwargs, onChange]);

  const setField = (k: string, v: unknown) => setKwargs((prev) => ({ ...prev, [k]: v }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          Advantage estimator
          {alias ? <Badge variant="secondary">{alias}</Badge> : null}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <p className="text-xs text-[var(--text-secondary)]">
          Picks the Phase 2 advantage estimator used during training.
          ReinforcePlusPlus (NeMo-RL port) is the default for cohort-driven
          rollouts; GRPO is the no-critic DeepSeek variant; GAE is the
          critic-based classic.
        </p>
        <div className="grid gap-1">
          <Label htmlFor="advantage-alias">Estimator</Label>
          <select
            id="advantage-alias"
            value={alias ?? ""}
            onChange={(e) => {
              const v = e.target.value || null;
              setAlias(v);
              setKwargs({});
            }}
            className="h-9 rounded-md border border-[var(--border-default)] bg-transparent px-2 font-mono text-sm"
          >
            <option value="">— Pick an estimator —</option>
            {(list.data ?? []).map((c) => (
              <option key={c.alias} value={c.alias}>
                {c.alias} ({c.source ?? "—"})
              </option>
            ))}
          </select>
        </div>
        {alias && detail.data ? (
          <>
            {detail.data.doc ? (
              <details>
                <summary className="cursor-pointer text-xs text-[var(--text-secondary)]">
                  docs
                </summary>
                <p className="mt-1 whitespace-pre-wrap text-xs">{detail.data.doc}</p>
              </details>
            ) : null}
            {detail.data.params
              .filter((p) => p.name !== "name")
              .map((p) => (
                <div key={p.name} className="flex flex-col gap-1">
                  <Label htmlFor={`adv-${p.name}`}>
                    <span className="font-mono text-xs">{p.name}</span>{" "}
                    <span className="text-[10px] text-[var(--text-secondary)]">
                      {p.annotation}
                    </span>
                  </Label>
                  <Input
                    id={`adv-${p.name}`}
                    value={String(kwargs[p.name] ?? p.default ?? "")}
                    onChange={(e) => setField(p.name, e.target.value)}
                    className="h-8 font-mono text-xs"
                  />
                </div>
              ))}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
