import { ArrowLeft, Pause, Play, RefreshCcw, RotateCw, Sliders } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { producersApi, type ProducerSummary, type ProducerLogs } from "@/lib/api/streaming";

export function ProducerDetail() {
  const { name = "" } = useParams<{ name: string }>();
  const decoded = decodeURIComponent(name);
  const [scaleValue, setScaleValue] = useState("1");

  const summary = useApiQuery<ProducerSummary>({
    queryKey: ["streaming", "producer", decoded],
    path: `/streaming/producers/${encodeURIComponent(decoded)}`,
    enabled: Boolean(decoded),
    refetchInterval: 30_000,
  });
  const logs = useApiQuery<ProducerLogs>({
    queryKey: ["streaming", "producer", decoded, "logs"],
    path: `/streaming/producers/${encodeURIComponent(decoded)}/logs`,
    query: { tail: 200 },
    enabled: Boolean(decoded),
    refetchInterval: 15_000,
  });

  const wrap = async (label: string, fn: () => Promise<unknown>) => {
    try {
      await fn();
      toast.success(`${label} ok`);
      summary.refetch();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    }
  };

  const metrics: Metric[] = [
    { label: "Status", value: null, hint: <Badge variant="secondary">{summary.data?.last_status ?? "—"}</Badge> },
    {
      label: "Replicas",
      value: summary.data?.current_replicas ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
      hint: <span>desired: {summary.data?.desired_replicas ?? "—"}</span>,
    },
    {
      label: "Topics",
      value: summary.data?.topics?.length ?? null,
      kind: "integer",
      digits: 0,
      tone: "neutral",
    },
    {
      label: "Enabled",
      value: null,
      hint: (
        <Badge variant={summary.data?.enabled ? "positive" : "warn"}>
          {summary.data?.enabled ? "yes" : "no"}
        </Badge>
      ),
    },
  ];

  return (
    <PageContainer
      title={decoded}
      subtitle="Producer detail: deployment + topics + recent logs. Start / stop / scale / restart through the supervisor."
      extra={
        <div className="flex items-center gap-2">
          <Link to="/streaming/producers">
            <Button variant="ghost" size="sm" className="gap-1">
              <ArrowLeft className="h-4 w-4" /> Back
            </Button>
          </Link>
          <Button variant="ghost" size="sm" onClick={() => summary.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button variant="ghost" size="sm" onClick={() => wrap("start", () => producersApi.start(decoded))} className="gap-1 text-[var(--pos-fg)]">
            <Play className="h-3.5 w-3.5" /> Start
          </Button>
          <Button variant="ghost" size="sm" onClick={() => wrap("stop", () => producersApi.stop(decoded))} className="gap-1 text-[var(--warn-fg)]">
            <Pause className="h-3.5 w-3.5" /> Stop
          </Button>
          <Button variant="ghost" size="sm" onClick={() => wrap("restart", () => producersApi.restart(decoded))} className="gap-1">
            <RotateCw className="h-3.5 w-3.5" /> Restart
          </Button>
        </div>
      }
    >
      <MetricsGrid metrics={metrics} columns={4} />

      <Card className="mt-3">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sliders className="h-4 w-4" /> Scale
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const r = Number(scaleValue);
              if (!Number.isFinite(r) || r < 0) {
                toast.error("Replica count must be a non-negative number");
                return;
              }
              void wrap("scale", () => producersApi.scale(decoded, r));
            }}
            className="flex flex-wrap items-end gap-3"
          >
            <div className="flex flex-col gap-1">
              <Label htmlFor="replicas">Replicas</Label>
              <Input
                id="replicas"
                type="number"
                min={0}
                value={scaleValue}
                onChange={(e) => setScaleValue(e.target.value)}
                className="w-32 font-mono"
              />
            </div>
            <Button type="submit">Apply</Button>
          </form>
        </CardContent>
      </Card>

      <Card className="mt-3">
        <CardHeader>
          <CardTitle>Topics</CardTitle>
          <Badge variant="secondary">{summary.data?.topics?.length ?? 0}</Badge>
        </CardHeader>
        <CardContent>
          <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {(summary.data?.topics ?? []).map((t) => (
              <li key={t} className="font-mono text-xs">{t}</li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card className="mt-3 h-[40vh]">
        <CardHeader>
          <CardTitle>Logs</CardTitle>
          <Badge variant="secondary">{logs.data?.lines?.length ?? 0} lines</Badge>
        </CardHeader>
        <CardContent className="h-full">
          <pre className="h-full overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-[10px]">
            {(logs.data?.lines ?? []).join("\n")}
          </pre>
        </CardContent>
      </Card>
    </PageContainer>
  );
}
