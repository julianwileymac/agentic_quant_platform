import { Activity, RefreshCcw } from "lucide-react";
import { Link } from "react-router-dom";

import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

interface RlRun {
  id: string;
  spec_name: string;
  spec_version_hash?: string;
  status: string;
  total_steps?: number;
  best_reward?: number;
  cost_usd?: number;
  started_at?: string;
  finished_at?: string | null;
}

const STATUS_TONE: Record<string, "positive" | "negative" | "warn" | "secondary"> = {
  completed: "positive",
  succeeded: "positive",
  failed: "negative",
  error: "negative",
  running: "warn",
  pending: "secondary",
  queued: "secondary",
};

export function RlRunsPage() {
  const list = useApiQuery<RlRun[]>({
    queryKey: ["rl", "runs"],
    path: "/rl/runs",
    query: { limit: 100 },
    select: (raw) => (Array.isArray(raw) ? (raw as RlRun[]) : []),
    refetchInterval: 30_000,
  });

  const columns: ColumnDef<RlRun>[] = [
    {
      key: "id",
      header: "Run",
      render: (r) => (
        <Link to={`/rl/runs/${encodeURIComponent(r.id)}`} className="font-mono text-xs hover:underline">
          {r.id.slice(0, 12)}
        </Link>
      ),
    },
    { key: "spec", header: "Spec", render: (r) => <span className="font-mono text-xs">{r.spec_name}</span> },
    {
      key: "status",
      header: "Status",
      width: 110,
      render: (r) => <Badge variant={STATUS_TONE[r.status] ?? "secondary"}>{r.status}</Badge>,
    },
    {
      key: "steps",
      header: "Steps",
      width: 110,
      align: "right",
      render: (r) => <Numeric value={r.total_steps ?? null} kind="integer" digits={0} color="neutral" />,
    },
    {
      key: "best_reward",
      header: "Best reward",
      width: 130,
      align: "right",
      render: (r) => <Numeric value={r.best_reward ?? null} kind="decimal" digits={3} color="auto" />,
    },
    {
      key: "cost_usd",
      header: "Cost",
      width: 110,
      align: "right",
      render: (r) => <Numeric value={r.cost_usd ?? null} kind="money" digits={3} color="auto" />,
    },
    {
      key: "started_at",
      header: "Started",
      width: 140,
      align: "right",
      render: (r) => (
        <span className="text-[var(--text-secondary)]">
          {r.started_at ? formatTime(r.started_at) : "—"}
        </span>
      ),
    },
    {
      key: "replay",
      header: "",
      width: 110,
      render: (r) => (
        <Link to={`/rl/runs/${encodeURIComponent(r.id)}/replay`}>
          <Button size="sm" variant="ghost" className="gap-1">
            <Activity className="h-3.5 w-3.5" /> Replay
          </Button>
        </Link>
      ),
    },
  ];

  return (
    <PageContainer
      title="RL Runs"
      subtitle="Recent RL training / evaluation / paper / replay runs across all specs. Click a row to drill into the run detail."
      extra={
        <Button variant="ghost" size="sm" onClick={() => list.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<RlRun>
            rows={list.data ?? []}
            rowKey={(r) => r.id}
            columns={columns}
            emptyState={list.isPending ? <span>Loading…</span> : <span>No RL runs yet.</span>}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
