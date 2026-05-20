import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type FlowResult, type FlowSchema } from "@/lib/analysis/api";

import { type DatasetSelection } from "./DatasetPicker";
import { FlowForm } from "./FlowForm";
import { FlowResultDisplay } from "./FlowResultDisplay";

interface Props {
  flows: FlowSchema[];
  dataset: DatasetSelection;
  /** Optional callback the page uses to support "Save as spec". */
  onResult?: ((flow: FlowSchema, result: FlowResult) => void) | undefined;
  /** Cross-link emitted in the header: deep link to a richer surface. */
  crossLink?: { href: string; label: string } | undefined;
}

/**
 * One tab in the Analysis Lab — picks a flow from the namespace,
 * renders its form, runs the preview, and shows the result inline.
 */
export function NamespaceTab({ flows, dataset, onResult, crossLink }: Props) {
  const sortedFlows = useMemo(
    () => [...flows].sort((a, b) => a.name.localeCompare(b.name)),
    [flows],
  );
  const [selected, setSelected] = useState<string>(sortedFlows[0]?.name ?? "");
  const [result, setResult] = useState<FlowResult | null>(null);

  useEffect(() => {
    if (!sortedFlows.find((f) => f.name === selected) && sortedFlows[0]) {
      setSelected(sortedFlows[0].name);
      setResult(null);
    }
  }, [sortedFlows, selected]);

  const flow = sortedFlows.find((f) => f.name === selected) ?? null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
      <aside className="rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2">
        <h3 className="mb-2 text-xs font-medium uppercase text-[var(--text-secondary)]">
          Flows
        </h3>
        <div className="flex flex-col gap-1">
          {sortedFlows.map((f) => (
            <button
              key={f.name}
              type="button"
              onClick={() => {
                setSelected(f.name);
                setResult(null);
              }}
              className={`flex flex-col items-start gap-0.5 rounded-md px-2 py-1.5 text-left text-xs transition ${
                f.name === selected
                  ? "bg-[var(--bg-elevated)] text-[var(--text-primary)]"
                  : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
              }`}
            >
              <span className="font-medium">{f.label}</span>
              <span className="font-mono text-[10px] opacity-75">{f.name}</span>
            </button>
          ))}
        </div>
      </aside>
      <section className="space-y-4">
        {flow ? (
          <>
            <header className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-medium">{flow.label}</h2>
                <p className="text-xs text-[var(--text-secondary)]">
                  {flow.description}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  <span className="font-mono text-[10px] text-[var(--text-secondary)]">
                    {flow.name}
                  </span>
                  {flow.tags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="text-[10px]">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
              {crossLink ? (
                <Button asChild size="sm" variant="outline">
                  <a href={crossLink.href}>{crossLink.label} →</a>
                </Button>
              ) : null}
            </header>
            <FlowForm
              flow={flow}
              dataset={dataset}
              onResult={(res) => {
                setResult(res);
                onResult?.(flow, res);
              }}
            />
            <FlowResultDisplay result={result} />
          </>
        ) : (
          <p className="text-xs text-[var(--text-secondary)]">
            No flows registered for this namespace.
          </p>
        )}
      </section>
    </div>
  );
}
