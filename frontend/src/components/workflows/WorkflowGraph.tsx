import type { WorkflowSpecDetail } from "@/lib/api/workflows";

/**
 * Minimal read-only graph view of a WorkflowSpec.
 *
 * Phase 5 of the additive orchestration refactor ships a textual
 * adjacency view. A richer react-flow rendering can be wired in
 * Phase 7 without changing the contract — the studio backend
 * already exposes the full `payload` on `/workflows/{name}`.
 */
export function WorkflowGraph({
  spec,
}: {
  spec: WorkflowSpecDetail | null;
}) {
  if (!spec) {
    return (
      <p className="text-sm text-muted-foreground">Loading workflow…</p>
    );
  }

  const params = (spec.payload?.params ?? {}) as Record<string, unknown>;
  const adapterKind =
    (spec.payload?.adapter_kind as string | null | undefined) ?? "—";
  const maxRounds = (spec.payload?.max_rounds as number | undefined) ?? 1;

  return (
    <div className="space-y-3 text-sm">
      <div>
        <span className="text-muted-foreground">Adapter alias: </span>
        <span className="font-mono">{spec.adapter}</span>
      </div>
      <div>
        <span className="text-muted-foreground">Adapter kind: </span>
        <span className="font-mono">{adapterKind}</span>
      </div>
      <div>
        <span className="text-muted-foreground">Max rounds: </span>
        <span className="font-mono tabular-nums">{maxRounds}</span>
      </div>
      {Object.keys(params).length > 0 ? (
        <div>
          <p className="text-muted-foreground">Params:</p>
          <pre className="mt-1 overflow-x-auto rounded bg-muted p-2 text-xs">
            {JSON.stringify(params, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
