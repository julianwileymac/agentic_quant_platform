import { ArrowLeft, Brain, NotebookPen, RefreshCcw, StopCircle } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { Numeric } from "@/components/common/Numeric";
import { ProgressTimeline } from "@/components/common/ProgressTimeline";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import {
  AgentsApi,
  type AgentDecision,
  type AgentReflection,
  type AgentRunDetail,
} from "@/lib/api/agents";
import { useChatStream } from "@/lib/ws";
import { formatTime } from "@/lib/utils";

export function AgentRunDetailRoute() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [confirmCancel, setConfirmCancel] = useState(false);

  const run = useApiQuery<AgentRunDetail>({
    queryKey: ["agent-run", id],
    path: `/agents/runs/${encodeURIComponent(id ?? "")}`,
    enabled: Boolean(id),
    refetchInterval: (q) => {
      const status = (q.state.data as AgentRunDetail | undefined)?.status;
      return status === "running" || status === "queued" ? 4_000 : false;
    },
  });
  const decisions = useApiQuery<AgentDecision[]>({
    queryKey: ["agent-run", id, "decisions"],
    path: `/agents/runs/${encodeURIComponent(id ?? "")}/decisions`,
    enabled: Boolean(id),
    refetchInterval: 6_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const reflections = useApiQuery<AgentReflection[]>({
    queryKey: ["agent-run", id, "reflections"],
    path: `/agents/runs/${encodeURIComponent(id ?? "")}/reflections`,
    enabled: Boolean(id),
    refetchInterval: 6_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const stream = useChatStream(id ?? null, "agents");

  if (!id) {
    return <PageContainer title="Agent Run" subtitle="Missing :id route param.">{null}</PageContainer>;
  }

  const r = run.data;
  const live = r?.status === "running" || r?.status === "queued";

  const metrics: Metric[] = [
    { label: "Status", value: null, hint: <Badge variant={live ? "default" : r?.status === "ok" || r?.status === "completed" ? "positive" : r?.status === "error" || r?.status === "failed" ? "negative" : "secondary"}>{r?.status ?? "—"}</Badge> },
    { label: "Cost", value: r?.cost_usd ?? null, kind: "money", digits: 4 },
    { label: "Tokens in", value: r?.tokens_in ?? null, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Tokens out", value: r?.tokens_out ?? null, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Tool calls", value: r?.n_tool_calls ?? null, kind: "integer", digits: 0, tone: "neutral" },
    { label: "RAG hits", value: r?.n_rag_hits ?? null, kind: "integer", digits: 0, tone: "neutral" },
    {
      label: "Guardrail fails",
      value: r?.guardrail_failures ?? null,
      kind: "integer",
      digits: 0,
      tone: (r?.guardrail_failures ?? 0) > 0 ? "force-neg" : "force-pos",
    },
    {
      label: "Started",
      value: null,
      hint: r?.started_at ? formatTime(r.started_at) : "—",
    },
  ];

  const cancel = async () => {
    try {
      await AgentsApi.cancelRun(id);
      toast.success(`Run ${id} cancelled`);
      run.refetch();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Cancel failed: ${msg}`);
      throw err;
    }
  };

  return (
    <PageContainer
      title={r?.spec_name ?? "Agent Run"}
      subtitle={
        <span className="font-mono text-xs">
          {id} · spec hash {r?.spec_version_hash ? r.spec_version_hash.slice(0, 12) : "—"}
        </span>
      }
      extra={
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate("/agents/runs")}>
            <ArrowLeft className="h-4 w-4" /> All runs
          </Button>
          <Button variant="ghost" size="sm" onClick={() => run.refetch()}>
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={!live}
            onClick={() => setConfirmCancel(true)}
            className="gap-2"
          >
            <StopCircle className="h-4 w-4" /> Cancel
          </Button>
        </div>
      }
    >
      <MetricsGrid metrics={metrics} columns={4} />

      <Tabs defaultValue="timeline" className="mt-4">
        <TabsList>
          <TabsTrigger value="timeline">
            <Brain className="mr-1 h-3.5 w-3.5" /> Timeline ({stream.events.length})
          </TabsTrigger>
          <TabsTrigger value="decisions">Decisions ({decisions.data?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="reflections">
            <NotebookPen className="mr-1 h-3.5 w-3.5" /> Reflections ({reflections.data?.length ?? 0})
          </TabsTrigger>
          <TabsTrigger value="raw">Raw</TabsTrigger>
        </TabsList>

        <TabsContent value="timeline">
          <ProgressTimeline events={stream.events} height={"60vh"} follow />
        </TabsContent>

        <TabsContent value="decisions">
          <Card>
            <CardContent className="p-0">
              <div className="h-[60vh]">
                <DataTable<AgentDecision>
                  rows={decisions.data ?? []}
                  rowKey={(d) => d.id}
                  emptyState={<span>No decisions emitted yet.</span>}
                  columns={[
                    {
                      key: "ts",
                      header: "Time",
                      width: 130,
                      render: (d) => (
                        <span className="text-[var(--text-secondary)]">{d.ts ? formatTime(d.ts) : "—"}</span>
                      ),
                    },
                    {
                      key: "vt_symbol",
                      header: "Symbol",
                      width: 130,
                      render: (d) => <span className="font-mono text-xs">{d.vt_symbol ?? "—"}</span>,
                    },
                    {
                      key: "action",
                      header: "Action",
                      width: 90,
                      render: (d) => (
                        <Badge
                          variant={
                            d.action?.toUpperCase() === "BUY"
                              ? "positive"
                              : d.action?.toUpperCase() === "SELL"
                                ? "negative"
                                : "secondary"
                          }
                        >
                          {d.action ?? "—"}
                        </Badge>
                      ),
                    },
                    {
                      key: "size_pct",
                      header: "Size %",
                      width: 100,
                      align: "right",
                      render: (d) => <Numeric value={d.size_pct ?? null} kind="percent" digits={2} color="auto" />,
                    },
                    {
                      key: "confidence",
                      header: "Confidence",
                      width: 110,
                      align: "right",
                      render: (d) => <Numeric value={d.confidence ?? null} kind="percent" digits={1} color="auto" />,
                    },
                    {
                      key: "rationale",
                      header: "Rationale",
                      render: (d) => <span className="text-xs italic">{d.rationale ?? "—"}</span>,
                    },
                  ]}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="reflections">
          <Card>
            <CardContent className="p-0">
              <ul className="divide-y divide-[var(--border-subtle)]">
                {(reflections.data ?? []).length === 0 ? (
                  <li className="px-4 py-6 text-center text-sm text-[var(--text-secondary)]">
                    No reflections logged.
                  </li>
                ) : (
                  (reflections.data ?? []).map((rfx) => (
                    <li key={rfx.id} className="px-4 py-3 text-sm">
                      <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
                        <span>{rfx.ts ? formatTime(rfx.ts) : "—"}</span>
                        {(rfx.tags ?? []).map((t) => (
                          <Badge key={t} variant="outline" className="text-[10px]">
                            {t}
                          </Badge>
                        ))}
                      </div>
                      <p className="mt-1 break-words">{rfx.text}</p>
                    </li>
                  ))
                )}
              </ul>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="raw">
          <Card>
            <CardHeader>
              <CardTitle>Raw run JSON</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words font-mono text-xs">
                {JSON.stringify(r ?? {}, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {confirmCancel ? (
        <ConfirmFrictionDialog
          open={confirmCancel}
          onOpenChange={setConfirmCancel}
          title={`Cancel run ${id}`}
          consequence="Sends a cancel signal to the agent runtime. In-flight tool calls may still complete; the agent_runs_v2 row will be marked cancelled."
          details={[
            { label: "Spec", value: r?.spec_name ?? "—" },
            { label: "Cost so far", value: r?.cost_usd != null ? `$${r.cost_usd.toFixed(4)}` : "—" },
            { label: "Tokens", value: ((r?.tokens_in ?? 0) + (r?.tokens_out ?? 0)).toLocaleString() },
          ]}
          confirmPhrase="CANCEL"
          confirmLabel="Cancel run"
          confirmVariant="destructive"
          onConfirm={cancel}
        />
      ) : null}

      <p className="mt-4 text-xs text-[var(--text-secondary)]">
        Need parent context? <Link className="text-[var(--info-fg)] underline" to="/agents/runs">Back to all runs</Link>.
      </p>
    </PageContainer>
  );
}
