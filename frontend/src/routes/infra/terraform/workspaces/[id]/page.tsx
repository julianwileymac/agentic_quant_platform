import { Play, RefreshCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { useApiQuery } from "@/lib/api/hooks";
import {
  type DescribeWorkspaceResponse,
  type TerraformRun,
  terraformApi,
} from "@/lib/api/terraform";
import { formatTime } from "@/lib/utils";

/**
 * Workspace detail — plan / apply / destroy lifecycle + recent runs +
 * state-version outputs.
 */
export function TerraformWorkspaceDetailRoute() {
  const { id = "" } = useParams<{ id: string }>();
  const [pending, setPending] = useState(false);
  const [destroyOpen, setDestroyOpen] = useState(false);

  const workspace = useApiQuery<DescribeWorkspaceResponse>({
    queryKey: ["terraform", "workspace", id],
    path: `/terraform/workspaces/${encodeURIComponent(id)}`,
    refetchInterval: 30_000,
    select: (raw) => raw as DescribeWorkspaceResponse,
  });

  const runs = useApiQuery<{ items: TerraformRun[]; total: number }>({
    queryKey: ["terraform", "workspace-runs", id],
    path: "/terraform/runs",
    query: { workspace_id: id, limit: 20 },
    refetchInterval: 15_000,
    select: (raw) => raw as { items: TerraformRun[]; total: number },
  });

  const ws = workspace.data?.workspace;
  const latestState = workspace.data?.latest_state_version;

  const plan = async () => {
    setPending(true);
    try {
      const result = await terraformApi.plan(id);
      toast.success(`Plan queued (run ${result.run_id})`);
    } catch (err) {
      toast.error("Plan failed", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setPending(false);
    }
  };

  const apply = async (planRun: TerraformRun) => {
    setPending(true);
    try {
      const result = await terraformApi.apply(id, planRun.id);
      toast.success(`Apply queued (run ${result.run_id})`);
    } catch (err) {
      toast.error("Apply failed", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setPending(false);
    }
  };

  const destroy = async () => {
    if (!ws) return;
    setPending(true);
    try {
      const result = await terraformApi.destroy(id, ws.slug);
      toast.success(`Destroy queued (run ${result.run_id})`);
    } catch (err) {
      toast.error("Destroy failed", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setPending(false);
    }
  };

  return (
    <PageContainer
      title={ws ? ws.name : "Workspace"}
      subtitle={ws ? `${ws.slug} · ${ws.environment} · ${ws.state_backend}` : "Loading…"}
      data-mode="infra"
      extra={
        <div className="flex items-center gap-2">
          <Button onClick={plan} disabled={pending} variant="default">
            <Play className="h-4 w-4" /> Plan
          </Button>
          <Button onClick={() => setDestroyOpen(true)} disabled={pending} variant="destructive">
            <Trash2 className="h-4 w-4" /> Destroy
          </Button>
          <Button
            onClick={() => {
              workspace.refetch();
              runs.refetch();
            }}
            variant="ghost"
          >
            <RefreshCcw className="h-4 w-4" />
          </Button>
        </div>
      }
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent runs</CardTitle>
          </CardHeader>
          <CardContent>
            {(runs.data?.items ?? []).length === 0 ? (
              <p className="text-xs text-[var(--text-secondary)]">No runs yet.</p>
            ) : (
              <ul className="space-y-1 text-xs">
                {(runs.data?.items ?? []).map((r) => (
                  <li
                    key={r.id}
                    className="flex items-center justify-between rounded-sm border border-[var(--border)] px-2 py-1"
                  >
                    <span className="font-mono">
                      {r.run_kind} · {r.id.slice(0, 8)}
                    </span>
                    <span className="flex items-center gap-2">
                      <Badge variant="outline">{r.status}</Badge>
                      <span className="text-[var(--text-secondary)]">
                        {r.started_at ? formatTime(r.started_at) : ""}
                      </span>
                      {r.status === "awaiting_approval" && r.run_kind === "plan" ? (
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => apply(r)}
                          disabled={pending}
                        >
                          Apply this plan
                        </Button>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Latest state outputs</CardTitle>
          </CardHeader>
          <CardContent className="text-xs">
            {latestState ? (
              <>
                <p className="mb-2 text-[var(--text-secondary)]">
                  serial = {latestState.serial}
                  {latestState.resource_count != null
                    ? ` · resources = ${latestState.resource_count}`
                    : ""}
                </p>
                <pre className="overflow-x-auto whitespace-pre-wrap font-mono">
                  {JSON.stringify(latestState.outputs_redacted, null, 2)}
                </pre>
              </>
            ) : (
              <p className="text-[var(--text-secondary)]">
                No applied state versions yet.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <ConfirmFrictionDialog
        open={destroyOpen}
        onOpenChange={setDestroyOpen}
        title={`Destroy workspace ${ws?.slug ?? id}?`}
        consequence="This will tear down every resource managed by this workspace. State files are preserved, but cloud resources are deleted. This cannot be reversed."
        confirmPhrase={ws?.slug ?? "CONFIRM"}
        confirmLabel="Destroy workspace"
        confirmVariant="destructive"
        onConfirm={destroy}
      />
    </PageContainer>
  );
}
