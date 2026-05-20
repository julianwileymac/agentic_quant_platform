import { ArrowLeft, RefreshCcw } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";

interface ReplayRow {
  step: number;
  reward: number;
  cum_reward?: number;
  action?: number | string;
  obs_summary?: Record<string, unknown>;
}

interface ReplayPayload {
  run_id: string;
  spec_name: string;
  total_steps: number;
  best_reward?: number;
  worst_reward?: number;
  trajectory: ReplayRow[];
}

export function RlReplayViewer() {
  const { id = "" } = useParams<{ id: string }>();
  const replay = useApiQuery<ReplayPayload>({
    queryKey: ["rl", "runs", id, "replay"],
    path: `/rl/runs/${encodeURIComponent(id)}/replay`,
    enabled: Boolean(id),
  });

  const metrics: Metric[] = [
    {
      label: "Spec",
      value: null,
      hint: <span className="font-mono text-xs">{replay.data?.spec_name ?? "—"}</span>,
    },
    { label: "Total steps", value: replay.data?.total_steps ?? null, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Best reward", value: replay.data?.best_reward ?? null, kind: "decimal", digits: 3, tone: "auto" },
    { label: "Worst reward", value: replay.data?.worst_reward ?? null, kind: "decimal", digits: 3, tone: "auto" },
  ];

  const columns: ColumnDef<ReplayRow>[] = [
    {
      key: "step",
      header: "Step",
      width: 110,
      align: "right",
      render: (r) => <Numeric value={r.step} kind="integer" digits={0} color="neutral" />,
    },
    {
      key: "action",
      header: "Action",
      width: 130,
      render: (r) => <span className="font-mono text-xs">{String(r.action ?? "—")}</span>,
    },
    {
      key: "reward",
      header: "Reward",
      width: 130,
      align: "right",
      render: (r) => <Numeric value={r.reward} kind="decimal" digits={4} color="auto" signed />,
    },
    {
      key: "cum_reward",
      header: "Cumulative",
      width: 140,
      align: "right",
      render: (r) => <Numeric value={r.cum_reward ?? null} kind="decimal" digits={3} color="auto" />,
    },
    {
      key: "obs",
      header: "Observation",
      render: (r) => (
        <span className="line-clamp-1 font-mono text-[10px] text-[var(--text-secondary)]">
          {JSON.stringify(r.obs_summary ?? {})}
        </span>
      ),
    },
  ];

  return (
    <PageContainer
      title={`RL replay ${id.slice(0, 12)}`}
      subtitle="Inspect a recorded RL trajectory step-by-step from the Iceberg trajectory store."
      extra={
        <div className="flex items-center gap-2">
          <Link to="/rl/runs">
            <Button variant="ghost" size="sm" className="gap-1">
              <ArrowLeft className="h-4 w-4" /> Back to runs
            </Button>
          </Link>
          <Button variant="ghost" size="sm" onClick={() => replay.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
        </div>
      }
    >
      <MetricsGrid metrics={metrics} columns={4} />

      <Card className="mt-3 h-[calc(100vh-280px)]">
        <CardHeader>
          <CardTitle>Trajectory</CardTitle>
          <Badge variant="secondary">{replay.data?.trajectory?.length ?? 0}</Badge>
        </CardHeader>
        <CardContent className="h-full p-0">
          <DataTable<ReplayRow>
            rows={replay.data?.trajectory ?? []}
            rowKey={(r) => String(r.step)}
            columns={columns}
            emptyState={replay.isPending ? <span>Loading…</span> : <span>No steps recorded.</span>}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
