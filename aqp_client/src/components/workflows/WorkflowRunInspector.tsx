import { Badge } from "@/components/ui/badge";

import type { WorkflowRunDetail } from "@/lib/api/workflows";

/**
 * Renders the ordered `adapter_breadcrumbs` produced by the
 * WorkflowRuntime for one run. Each crumb carries the adapter
 * alias, node name, status, and duration_ms — enough for an
 * operator to spot where the run halted / errored / capped.
 */
export function WorkflowRunInspector({
  run,
}: {
  run: WorkflowRunDetail | null;
}) {
  if (!run) {
    return <p className="text-sm text-muted-foreground">Loading run…</p>;
  }
  if (!run.breadcrumbs || run.breadcrumbs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No breadcrumbs yet — the runtime emits them per adapter transition.
      </p>
    );
  }
  return (
    <ol className="space-y-2">
      {run.breadcrumbs.map((b, idx) => (
        <li
          key={`${b.adapter}-${b.node}-${idx}`}
          className="flex items-center justify-between rounded border p-2 text-sm"
        >
          <div>
            <span className="font-mono text-xs text-muted-foreground">
              {idx + 1}.
            </span>{" "}
            <span className="font-medium">{b.adapter}</span>{" "}
            <span className="text-muted-foreground">·</span>{" "}
            <span className="font-mono text-xs">{b.node}</span>
          </div>
          <div className="flex items-center gap-3">
            {typeof b.duration_ms === "number" ? (
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {b.duration_ms.toFixed(1)} ms
              </span>
            ) : null}
            <Badge
              variant={
                b.status === "ok"
                  ? "default"
                  : b.status === "halted"
                    ? "negative"
                    : b.status === "capped"
                      ? "outline"
                      : "secondary"
              }
            >
              {b.status}
            </Badge>
          </div>
        </li>
      ))}
    </ol>
  );
}
