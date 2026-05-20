import { ArrowLeft, RefreshCcw, StopCircle } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { flinkApi, type FlinkSessionJob } from "@/lib/api/streaming";

export function FlinkJobDetail() {
  const { name = "" } = useParams<{ name: string }>();
  const decoded = decodeURIComponent(name);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const job = useApiQuery<FlinkSessionJob>({
    queryKey: ["streaming", "flink", "session-job", decoded],
    path: `/streaming/flink/sessionjobs/${encodeURIComponent(decoded)}`,
    enabled: Boolean(decoded),
    refetchInterval: 30_000,
  });
  const exceptions = useApiQuery({
    queryKey: ["streaming", "flink", "job", decoded, "exceptions"],
    path: job.data?.job_id
      ? `/streaming/flink/jobs/${encodeURIComponent(job.data.job_id)}/exceptions`
      : "/streaming/flink/jobs/_disabled/exceptions",
    enabled: Boolean(job.data?.job_id),
  });

  const submitDelete = async () => {
    try {
      await flinkApi.deleteSessionJob(decoded, job.data?.namespace);
      toast.success(`Session job ${decoded} deleted`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setConfirmDelete(false);
    }
  };

  const submitSuspend = async () => {
    try {
      await flinkApi.suspendSessionJob(decoded);
      toast.success("Suspended");
      job.refetch();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };
  const submitActivate = async () => {
    try {
      await flinkApi.activateSessionJob(decoded);
      toast.success("Activated");
      job.refetch();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  const metrics: Metric[] = [
    { label: "State", value: null, hint: <Badge variant="secondary">{job.data?.state ?? "—"}</Badge> },
    {
      label: "Parallelism",
      value: job.data?.parallelism ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
    { label: "Namespace", value: null, hint: <span className="font-mono text-xs">{job.data?.namespace ?? "—"}</span> },
    { label: "Job id", value: null, hint: <span className="font-mono text-xs">{job.data?.job_id ?? "—"}</span> },
  ];

  return (
    <PageContainer
      title={decoded}
      subtitle="FlinkSessionJob CRD detail. Lifecycle controls (activate / suspend / delete) plus exception trail from the Flink REST API."
      extra={
        <div className="flex items-center gap-2">
          <Link to="/streaming/flink">
            <Button variant="ghost" size="sm" className="gap-1">
              <ArrowLeft className="h-4 w-4" /> Back
            </Button>
          </Link>
          <Button variant="ghost" size="sm" onClick={() => job.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={submitSuspend}>
            Suspend
          </Button>
          <Button variant="outline" size="sm" onClick={submitActivate}>
            Activate
          </Button>
          <Button variant="warn" size="sm" onClick={() => setConfirmDelete(true)} className="gap-1">
            <StopCircle className="h-4 w-4" /> Delete
          </Button>
        </div>
      }
    >
      <MetricsGrid metrics={metrics} columns={4} />

      <Card className="mt-3">
        <CardHeader>
          <CardTitle>Spec</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="max-h-[40vh] overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs">
            {JSON.stringify(job.data?.raw ?? {}, null, 2)}
          </pre>
        </CardContent>
      </Card>

      <Card className="mt-3">
        <CardHeader>
          <CardTitle>Exceptions</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="max-h-[30vh] overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs">
            {JSON.stringify(exceptions.data ?? {}, null, 2)}
          </pre>
        </CardContent>
      </Card>

      {confirmDelete ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(o) => !o && setConfirmDelete(false)}
          title={`Delete session job ${decoded}`}
          consequence="Removes the FlinkSessionJob CRD. The Flink JobManager will cancel the job and forget its checkpoints unless an external savepoint was triggered first."
          details={[
            { label: "Namespace", value: job.data?.namespace ?? "?" },
            { label: "Job id", value: job.data?.job_id ?? "—" },
          ]}
          confirmPhrase="DELETE"
          confirmLabel="Delete"
          confirmVariant="destructive"
          onConfirm={submitDelete}
        />
      ) : null}
    </PageContainer>
  );
}
