import { Activity, RefreshCcw } from "lucide-react";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

interface MonitoringRun {
  task_id: string;
  name: string;
  state: string;
  worker?: string;
  started_at?: string;
  duration_ms?: number;
  position?: "active" | "reserved" | "scheduled";
}

interface ServiceHealth {
  name: string;
  ok: boolean;
  detail?: string;
  latency_ms?: number;
}

export function MonitorRoute() {
  const runs = useApiQuery<MonitoringRun[]>({
    queryKey: ["monitor", "runs"],
    path: "/monitor/runs",
    refetchInterval: 3_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const services = useApiQuery<ServiceHealth[]>({
    queryKey: ["monitor", "services"],
    path: "/monitor/services",
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  return (
    <PageContainer
      title="Monitor"
      subtitle="Celery + service health. Refreshes every 3-5 seconds."
      extra={
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            runs.refetch();
            services.refetch();
          }}
        >
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        {(services.data ?? []).map((svc) => (
          <Card key={svc.name}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {svc.name}
                <Badge variant={svc.ok ? "positive" : "negative"}>
                  {svc.ok ? "OK" : "Down"}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-[var(--text-secondary)]">
              {svc.detail ?? "—"}
              <div className="mt-1 flex items-center justify-between">
                <span>Latency</span>
                <Numeric value={svc.latency_ms ?? null} kind="decimal" digits={0} color="neutral" suffix=" ms" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card className="mt-4 h-[calc(100vh-360px)]">
        <CardHeader>
          <CardTitle>Active / reserved Celery runs</CardTitle>
          <Badge variant="secondary">{runs.data?.length ?? 0}</Badge>
        </CardHeader>
        <CardContent className="h-full p-0">
          <DataTable<MonitoringRun>
            rows={runs.data ?? []}
            rowKey={(r) => r.task_id}
            emptyState={
              <div className="flex flex-col items-center gap-2">
                <Activity className="h-6 w-6" />
                <span>No active runs.</span>
              </div>
            }
            columns={[
              {
                key: "name",
                header: "Task",
                render: (r) => (
                  <div className="flex flex-col">
                    <span className="font-medium">{r.name}</span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">{r.task_id}</span>
                  </div>
                ),
              },
              {
                key: "state",
                header: "State",
                width: 110,
                render: (r) => (
                  <Badge
                    variant={
                      r.state === "STARTED"
                        ? "default"
                        : r.state === "SUCCESS"
                          ? "positive"
                          : r.state === "FAILURE"
                            ? "negative"
                            : "secondary"
                    }
                  >
                    {r.state}
                  </Badge>
                ),
              },
              {
                key: "position",
                header: "Position",
                width: 100,
                render: (r) => <span className="text-xs">{r.position ?? "—"}</span>,
              },
              {
                key: "worker",
                header: "Worker",
                width: 200,
                render: (r) => <span className="font-mono text-xs">{r.worker ?? "—"}</span>,
              },
              {
                key: "duration_ms",
                header: "Elapsed",
                width: 110,
                align: "right",
                render: (r) => (
                  <Numeric value={r.duration_ms ?? null} kind="integer" digits={0} color="neutral" suffix=" ms" />
                ),
              },
              {
                key: "started_at",
                header: "Started",
                width: 130,
                align: "right",
                render: (r) => (
                  <span className="text-[var(--text-secondary)]">{r.started_at ? formatTime(r.started_at) : "—"}</span>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
