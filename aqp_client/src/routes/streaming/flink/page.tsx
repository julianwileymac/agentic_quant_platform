import { RefreshCcw, StopCircle, Zap } from "lucide-react";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import {
  flinkApi,
  type FlinkClusterOverview,
  type FlinkJob,
  type FlinkSessionJob,
} from "@/lib/api/flink";
import { formatTime } from "@/lib/utils";

const STATE_TONE: Record<string, "positive" | "negative" | "warn" | "secondary"> = {
  RUNNING: "positive",
  FINISHED: "secondary",
  FAILED: "negative",
  CANCELED: "warn",
  CANCELLED: "warn",
};

export function FlinkRoute() {
  const [confirmCancel, setConfirmCancel] = useState<FlinkJob | null>(null);

  const cluster = useApiQuery<FlinkClusterOverview>({
    queryKey: ["flink", "cluster"],
    path: "/streaming/flink/cluster",
    refetchInterval: 10_000,
  });
  const jobs = useApiQuery<FlinkJob[]>({
    queryKey: ["flink", "jobs"],
    path: "/streaming/flink/jobs",
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const sessionJobs = useApiQuery<FlinkSessionJob[]>({
    queryKey: ["flink", "session-jobs"],
    path: "/streaming/flink/session-jobs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const ov = cluster.data;
  const metrics: Metric[] = [
    { label: "Task managers", value: ov?.taskmanagers ?? null, kind: "integer", digits: 0, tone: "neutral" },
    {
      label: "Slots (avail / total)",
      value: null,
      hint: ov ? `${ov.slots_available} / ${ov.slots_total}` : "—",
    },
    { label: "Running", value: ov?.jobs_running ?? null, kind: "integer", digits: 0, tone: "force-pos" },
    { label: "Finished", value: ov?.jobs_finished ?? null, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Failed", value: ov?.jobs_failed ?? null, kind: "integer", digits: 0, tone: "force-neg" },
    { label: "Cancelled", value: ov?.jobs_cancelled ?? null, kind: "integer", digits: 0, tone: "neutral" },
  ];

  const submitCancel = async () => {
    if (!confirmCancel) return;
    try {
      await flinkApi.cancelJob(confirmCancel.jid);
      toast.success(`Job ${confirmCancel.name} cancelled`);
      jobs.refetch();
      cluster.refetch();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Cancel failed: ${msg}`);
    } finally {
      setConfirmCancel(null);
    }
  };

  return (
    <PageContainer
      title="Flink"
      subtitle="Cluster overview + jobs (REST) and FlinkSessionJob CRDs (Kubernetes operator). Cancellation is friction-gated."
      extra={
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            cluster.refetch();
            jobs.refetch();
            sessionJobs.refetch();
          }}
        >
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <MetricsGrid metrics={metrics} columns={6} />

      <Card className="mt-4 h-[40vh]">
        <CardContent className="h-full p-0">
          <DataTable<FlinkJob>
            rows={jobs.data ?? []}
            rowKey={(j) => j.jid}
            emptyState={jobs.isPending ? <span>Loading jobs…</span> : <span>No Flink jobs.</span>}
            columns={[
              {
                key: "name",
                header: "Job",
                render: (j) => (
                  <div className="flex flex-col">
                    <span className="font-medium">{j.name}</span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">{j.jid}</span>
                  </div>
                ),
              },
              {
                key: "state",
                header: "State",
                width: 110,
                render: (j) => (
                  <Badge variant={STATE_TONE[j.state.toUpperCase()] ?? "secondary"}>{j.state}</Badge>
                ),
              },
              {
                key: "tasks",
                header: "Tasks",
                width: 110,
                align: "right",
                render: (j) => (
                  <Numeric
                    value={
                      j.tasks
                        ? Object.values(j.tasks).reduce((acc, n) => acc + (n ?? 0), 0)
                        : null
                    }
                    kind="integer"
                    digits={0}
                    color="neutral"
                  />
                ),
              },
              {
                key: "duration",
                header: "Duration (ms)",
                width: 130,
                align: "right",
                render: (j) => (
                  <Numeric value={j.duration ?? null} kind="integer" digits={0} color="neutral" />
                ),
              },
              {
                key: "started",
                header: "Started",
                width: 140,
                align: "right",
                render: (j) => (
                  <span className="text-[var(--text-secondary)]">
                    {j.start_time ? formatTime(new Date(j.start_time).toISOString()) : "—"}
                  </span>
                ),
              },
              {
                key: "actions",
                header: "Actions",
                width: 130,
                render: (j) => (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmCancel(j);
                    }}
                    disabled={j.state.toUpperCase() !== "RUNNING"}
                    className="gap-1 text-[var(--warn-fg)]"
                  >
                    <StopCircle className="h-3.5 w-3.5" /> Cancel
                  </Button>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>

      <Card className="mt-4 h-[35vh]">
        <CardContent className="h-full p-0">
          <DataTable<FlinkSessionJob>
            rows={sessionJobs.data ?? []}
            rowKey={(s) => `${s.namespace ?? ""}.${s.name}`}
            emptyState={
              <div className="flex flex-col items-center gap-2">
                <Zap className="h-6 w-6" />
                <span>No FlinkSessionJob CRDs.</span>
              </div>
            }
            columns={[
              {
                key: "name",
                header: "Session job",
                render: (s) => (
                  <div className="flex flex-col">
                    <span className="font-mono">{s.name}</span>
                    <span className="text-[10px] text-[var(--text-muted)]">{s.namespace ?? "default"}</span>
                  </div>
                ),
              },
              {
                key: "state",
                header: "State",
                width: 130,
                render: (s) => <Badge variant="secondary">{s.state ?? "—"}</Badge>,
              },
              {
                key: "job_id",
                header: "Job id",
                width: 200,
                render: (s) => <span className="font-mono text-xs">{s.job_id ?? "—"}</span>,
              },
              {
                key: "parallelism",
                header: "Parallelism",
                width: 130,
                align: "right",
                render: (s) => (
                  <Numeric
                    value={s.parallelism ?? null}
                    kind="integer"
                    digits={0}
                    color="neutral"
                  />
                ),
              },
              {
                key: "entry_class",
                header: "Entry class",
                width: 200,
                render: (s) => (
                  <span className="font-mono text-xs text-[var(--text-secondary)]">
                    {s.entry_class ?? "—"}
                  </span>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>

      {confirmCancel ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setConfirmCancel(null)}
          title={`Cancel Flink job ${confirmCancel.name}`}
          consequence="Sends a cancellation signal to the Flink JobManager. Stateful operators will checkpoint to the configured state backend before exiting."
          details={[
            { label: "Job", value: confirmCancel.name },
            { label: "JID", value: confirmCancel.jid },
            {
              label: "Tasks",
              value: confirmCancel.tasks
                ? Object.values(confirmCancel.tasks).reduce((acc, n) => acc + (n ?? 0), 0)
                : "—",
            },
          ]}
          confirmPhrase="CANCEL"
          confirmLabel="Cancel job"
          confirmVariant="warn"
          onConfirm={submitCancel}
        />
      ) : null}
    </PageContainer>
  );
}
