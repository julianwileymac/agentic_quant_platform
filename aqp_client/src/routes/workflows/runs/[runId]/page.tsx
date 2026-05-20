import { useState } from "react";
import { useParams } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { WorkflowRunInspector } from "@/components/workflows/WorkflowRunInspector";
import { useApiQuery } from "@/lib/api/hooks";
import {
  replayWorkflowRun,
  type WorkflowRunDetail,
} from "@/lib/api/workflows";

export function WorkflowRunRoute() {
  const { runId = "" } = useParams<{ runId: string }>();
  const [replaying, setReplaying] = useState(false);
  const [replayTaskId, setReplayTaskId] = useState<string | null>(null);
  const run = useApiQuery<WorkflowRunDetail>({
    queryKey: ["workflows", "run", runId],
    path: `/workflows/runs/${encodeURIComponent(runId)}`,
    refetchInterval: 3_000,
  });

  async function handleReplay() {
    setReplaying(true);
    try {
      const result = await replayWorkflowRun(runId);
      setReplayTaskId(result.task_id);
    } finally {
      setReplaying(false);
    }
  }

  return (
    <PageContainer
      title={`Workflow run ${runId.slice(0, 8)}…`}
      subtitle={run.data?.workflow_spec_name ?? "Loading…"}
    >
      <Card>
        <CardHeader>
          <CardTitle>Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div>
            <span className="text-muted-foreground">Status: </span>
            <span className="font-mono">{run.data?.status ?? "—"}</span>
          </div>
          <div>
            <span className="text-muted-foreground">Cost: </span>
            <span className="font-mono tabular-nums">
              ${run.data?.cost_usd?.toFixed(4) ?? "0.0000"}
            </span>
          </div>
          <div>
            <span className="text-muted-foreground">Duration: </span>
            <span className="font-mono tabular-nums">
              {run.data?.duration_ms?.toFixed(1) ?? "—"} ms
            </span>
          </div>
          <Button onClick={handleReplay} disabled={replaying} variant="secondary">
            {replaying ? "Replaying…" : "Replay run"}
          </Button>
          {replayTaskId ? (
            <p className="font-mono text-xs text-muted-foreground">
              Replay enqueued: {replayTaskId}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Breadcrumbs</CardTitle>
        </CardHeader>
        <CardContent>
          <WorkflowRunInspector run={run.data ?? null} />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
