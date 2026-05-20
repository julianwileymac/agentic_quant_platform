import { useState } from "react";
import { useParams } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WorkflowGraph } from "@/components/workflows/WorkflowGraph";
import { useApiQuery } from "@/lib/api/hooks";
import {
  runWorkflow,
  type WorkflowSpecDetail,
  type WorkflowSpecVersion,
} from "@/lib/api/workflows";

export function WorkflowDetailRoute() {
  const { name = "" } = useParams<{ name: string }>();
  const [submitting, setSubmitting] = useState(false);
  const [lastTaskId, setLastTaskId] = useState<string | null>(null);
  const spec = useApiQuery<WorkflowSpecDetail>({
    queryKey: ["workflows", "detail", name],
    path: `/workflows/${encodeURIComponent(name)}`,
  });
  const versions = useApiQuery<WorkflowSpecVersion[]>({
    queryKey: ["workflows", "versions", name],
    path: `/workflows/${encodeURIComponent(name)}/versions`,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  async function handleRun() {
    setSubmitting(true);
    try {
      const result = await runWorkflow(name, { spec_name: name });
      setLastTaskId(result.task_id);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageContainer
      title={spec.data?.name ?? name}
      subtitle={spec.data?.description ?? "Workflow detail"}
    >
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Spec</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div>
              <span className="text-muted-foreground">Adapter: </span>
              <span className="font-mono">{spec.data?.adapter}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Hash: </span>
              <span className="font-mono text-xs">
                {spec.data?.snapshot_hash?.slice(0, 12)}…
              </span>
            </div>
            <Button onClick={handleRun} disabled={submitting}>
              {submitting ? "Submitting…" : "Run workflow"}
            </Button>
            {lastTaskId ? (
              <p className="font-mono text-xs text-muted-foreground">
                Enqueued task {lastTaskId}
              </p>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Graph (read-only)</CardTitle>
          </CardHeader>
          <CardContent>
            <WorkflowGraph spec={spec.data ?? null} />
          </CardContent>
        </Card>
      </div>
      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Version history</CardTitle>
        </CardHeader>
        <CardContent>
          {versions.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : !versions.data || versions.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No versions persisted yet. Run the workflow once with{" "}
              <code>AQP_ORCHESTRATION_WORKFLOW_VERSIONING_ENABLED=true</code> to
              snapshot.
            </p>
          ) : (
            <ul className="divide-y">
              {versions.data.map((v) => (
                <li
                  key={v.id}
                  className="flex items-center justify-between py-2 font-mono text-xs"
                >
                  <span>v{v.version}</span>
                  <span>{v.spec_hash.slice(0, 16)}…</span>
                  <span>{v.created_at}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
