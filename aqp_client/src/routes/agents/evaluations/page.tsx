import { type ColumnDef, DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import type { AgentEvaluation } from "@/lib/api/agents";
import { formatTime } from "@/lib/utils";

export function AgentEvaluationsRoute() {
  const list = useApiQuery<AgentEvaluation[]>({
    queryKey: ["agents", "evaluations"],
    path: "/agents/evaluations",
    query: { limit: 100 },
    select: (raw) => (Array.isArray(raw) ? (raw as AgentEvaluation[]) : []),
  });

  const columns: ColumnDef<AgentEvaluation>[] = [
    {
      key: "spec_name",
      header: "Spec",
      render: (r) => <span className="font-mono">{r.spec_name}</span>,
    },
    {
      key: "eval_set_name",
      header: "Eval set",
      render: (r) => <span className="font-mono text-xs">{r.eval_set_name}</span>,
    },
    {
      key: "n_cases",
      header: "Cases",
      width: 110,
      align: "right",
      render: (r) => <Numeric value={r.n_cases} kind="integer" digits={0} color="neutral" />,
    },
    {
      key: "n_passed",
      header: "Passed",
      width: 110,
      align: "right",
      render: (r) => <Numeric value={r.n_passed} kind="integer" digits={0} color="neutral" />,
    },
    {
      key: "pass_rate",
      header: "Pass rate",
      width: 130,
      align: "right",
      render: (r) => {
        const rate = r.n_cases ? (r.n_passed / r.n_cases) : 0;
        const tone = rate >= 0.8 ? "positive" : rate >= 0.5 ? "warn" : "negative";
        return (
          <Badge variant={tone} className="font-mono">
            {(rate * 100).toFixed(1)}%
          </Badge>
        );
      },
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
      key: "completed_at",
      header: "Completed",
      width: 140,
      align: "right",
      render: (r) => (
        <span className="text-[var(--text-secondary)]">
          {r.completed_at ? formatTime(r.completed_at) : "—"}
        </span>
      ),
    },
  ];

  return (
    <PageContainer
      title="Agent Evaluations"
      subtitle="Spec-driven evaluation runs. Each row is a curated eval-set executed against an agent spec; pass-rate aggregates across cases."
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<AgentEvaluation>
            rows={list.data ?? []}
            rowKey={(r) => r.id}
            columns={columns}
            emptyState={
              list.isPending ? <span>Loading…</span> : <span>No evaluations recorded yet.</span>
            }
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
