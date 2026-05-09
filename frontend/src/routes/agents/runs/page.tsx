import { Activity, RefreshCcw } from "lucide-react";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import { formatTime } from "@/lib/utils";

interface AgentRun {
  id: string;
  spec_name?: string;
  spec_version_hash?: string;
  status?: string;
  started_at?: string;
  ended_at?: string;
  cost_usd?: number;
  tokens_in?: number;
  tokens_out?: number;
  guardrail_failures?: number;
}

export function AgentsRunsRoute() {
  const runs = useApiQuery<AgentRun[]>({
    queryKey: ["agent-runs"],
    path: "/agents/runs",
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  return (
    <PageContainer
      title="Agent Runs"
      subtitle="Spec-driven agent runs (agent_runs_v2). Each entry is the AgentRuntime ledger row for a single execution."
      extra={
        <Button variant="ghost" size="sm" onClick={() => runs.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <Card className="h-[calc(100vh-180px)]">
        <CardContent className="h-full p-0">
          <DataTable<AgentRun>
            rows={runs.data ?? []}
            rowKey={(r) => r.id}
            emptyState={
              runs.isPending ? (
                <span>Loading runs…</span>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Activity className="h-6 w-6" />
                  <span>No agent runs yet.</span>
                </div>
              )
            }
            columns={[
              {
                key: "spec",
                header: "Spec",
                render: (r) => (
                  <div className="flex flex-col">
                    <span className="font-medium">{r.spec_name ?? "—"}</span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">
                      {r.spec_version_hash ? r.spec_version_hash.slice(0, 12) : "—"}
                    </span>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                width: 110,
                render: (r) => (
                  <Badge
                    variant={
                      r.status === "ok"
                        ? "positive"
                        : r.status === "running"
                          ? "default"
                          : r.status === "error"
                            ? "negative"
                            : r.status === "halted"
                              ? "warn"
                              : "secondary"
                    }
                  >
                    {r.status ?? "—"}
                  </Badge>
                ),
              },
              {
                key: "guardrail_failures",
                header: "GR Fails",
                width: 100,
                align: "right",
                render: (r) => (
                  <Numeric
                    value={r.guardrail_failures ?? null}
                    kind="integer"
                    digits={0}
                    color={(r.guardrail_failures ?? 0) > 0 ? "force-neg" : "neutral"}
                  />
                ),
              },
              {
                key: "tokens_in",
                header: "Tokens in",
                width: 100,
                align: "right",
                render: (r) => <Numeric value={r.tokens_in ?? null} kind="integer" digits={0} color="neutral" />,
              },
              {
                key: "tokens_out",
                header: "Tokens out",
                width: 100,
                align: "right",
                render: (r) => <Numeric value={r.tokens_out ?? null} kind="integer" digits={0} color="neutral" />,
              },
              {
                key: "cost",
                header: "Cost",
                width: 110,
                align: "right",
                render: (r) => <Numeric value={r.cost_usd ?? null} kind="money" digits={3} color="auto" />,
              },
              {
                key: "started_at",
                header: "Started",
                width: 130,
                align: "right",
                render: (r) => (
                  <span className="text-[var(--text-secondary)]">
                    {r.started_at ? formatTime(r.started_at) : "—"}
                  </span>
                ),
              },
            ]}
          />
        </CardContent>
      </Card>
    </PageContainer>
  );
}
