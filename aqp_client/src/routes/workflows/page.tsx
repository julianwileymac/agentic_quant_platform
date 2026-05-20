import { Link } from "react-router-dom";
import { useMemo } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import type {
  WorkflowRunSummary,
  WorkflowSpecSummary,
} from "@/lib/api/workflows";

export function WorkflowsHomeRoute() {
  const workflows = useApiQuery<WorkflowSpecSummary[]>({
    queryKey: ["workflows", "list"],
    path: "/workflows",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const runs = useApiQuery<WorkflowRunSummary[]>({
    queryKey: ["workflows", "runs", "recent"],
    path: "/workflows/runs",
    query: { limit: 25 },
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const totals = useMemo(() => {
    const list = runs.data ?? [];
    const active = list.filter(
      (r) => r.status === "running" || r.status === "pending",
    ).length;
    const halted = list.filter((r) => r.halted).length;
    return { active, halted };
  }, [runs.data]);

  return (
    <PageContainer
      title="Workflows"
      subtitle="Hash-locked WorkflowSpecs dispatched via WorkflowRuntime + the OrchestrationAdapter registry. Replayable end-to-end."
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Workflows</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tabular-nums">
            {workflows.data?.length ?? 0}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Active runs</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tabular-nums">
            {totals.active}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Halted (recent)</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tabular-nums">
            {totals.halted}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Registry</CardTitle>
        </CardHeader>
        <CardContent>
          {workflows.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : !workflows.data || workflows.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No workflows registered yet. Drop a YAML under{" "}
              <code>configs/workflows/</code> or POST to <code>/workflows</code>.
            </p>
          ) : (
            <ul className="divide-y">
              {workflows.data.map((w) => (
                <li
                  key={w.name}
                  className="flex items-center justify-between py-2"
                >
                  <div>
                    <Link
                      to={`/workflows/specs/${encodeURIComponent(w.name)}`}
                      className="font-medium hover:underline"
                    >
                      {w.name}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      {w.description || "(no description)"}
                    </p>
                  </div>
                  <Badge variant="outline">{w.adapter}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
        </CardHeader>
        <CardContent>
          {!runs.data || runs.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No runs yet. Trigger one from a workflow detail page.
            </p>
          ) : (
            <ul className="divide-y">
              {runs.data.map((r) => (
                <li
                  key={r.id}
                  className="flex items-center justify-between py-2"
                >
                  <Link
                    to={`/workflows/runs/${r.id}`}
                    className="font-mono text-xs hover:underline"
                  >
                    {r.id.slice(0, 8)}…
                  </Link>
                  <span className="text-xs text-muted-foreground">
                    {r.workflow_spec_name}
                  </span>
                  <Badge
                    variant={
                      r.status === "halted"
                        ? "negative"
                        : r.status === "completed"
                          ? "default"
                          : "secondary"
                    }
                  >
                    {r.status}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
