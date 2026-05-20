import { ArrowLeft, RefreshCcw } from "lucide-react";
import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EquityChart } from "@/components/charts/EquityChart";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { ProgressTimeline } from "@/components/common/ProgressTimeline";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import type {
  RLActionPoint,
  RLEquityPoint,
  RLRewardTerm,
  RLRunDetail,
} from "@/lib/api/rl";
import { useChatStream } from "@/lib/ws";

export function RlRunDetailRoute() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const run = useApiQuery<RLRunDetail>({
    queryKey: ["rl-run", id],
    path: `/rl/runs/${encodeURIComponent(id ?? "")}`,
    enabled: Boolean(id),
    refetchInterval: (q) => {
      const status = (q.state.data as RLRunDetail | undefined)?.status;
      return status === "running" || status === "queued" ? 4_000 : false;
    },
  });
  const equity = useApiQuery<RLEquityPoint[]>({
    queryKey: ["rl-run", id, "equity"],
    path: `/rl/runs/${encodeURIComponent(id ?? "")}/equity`,
    enabled: Boolean(id),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const reward = useApiQuery<RLRewardTerm[]>({
    queryKey: ["rl-run", id, "reward"],
    path: `/rl/runs/${encodeURIComponent(id ?? "")}/reward-decomp`,
    enabled: Boolean(id),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const actions = useApiQuery<RLActionPoint[]>({
    queryKey: ["rl-run", id, "actions"],
    path: `/rl/runs/${encodeURIComponent(id ?? "")}/actions`,
    enabled: Boolean(id),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const stream = useChatStream(id ?? null, "chat");

  const equityForChart = useMemo(
    () => (equity.data ?? []).map((p) => ({ timestamp: p.episode, value: p.equity })),
    [equity.data],
  );

  // Pivot reward decomposition long-form -> wide-form for stacked area.
  const rewardWide = useMemo(() => {
    const list = reward.data ?? [];
    const byStep = new Map<number, Record<string, number | string>>();
    const termSet = new Set<string>();
    for (const term of list) {
      termSet.add(term.term);
      if (!byStep.has(term.step)) byStep.set(term.step, { step: term.step });
      const row = byStep.get(term.step)!;
      row[term.term] = term.value;
    }
    return {
      rows: Array.from(byStep.values()).sort((a, b) => Number(a.step) - Number(b.step)),
      terms: Array.from(termSet),
    };
  }, [reward.data]);

  const actionRows = useMemo(() => {
    const list = actions.data ?? [];
    const byAction = new Map<string, number>();
    for (const a of list) {
      byAction.set(a.action, (byAction.get(a.action) ?? 0) + a.count);
    }
    return Array.from(byAction.entries()).map(([action, count]) => ({ action, count }));
  }, [actions.data]);

  const r = run.data;

  const metrics: Metric[] = [
    {
      label: "Status",
      value: null,
      hint: <Badge variant={r?.status === "completed" ? "positive" : r?.status === "failed" ? "negative" : "default"}>{r?.status ?? "—"}</Badge>,
    },
    { label: "Algo", value: null, hint: r?.algo ?? "—" },
    { label: "Env", value: null, hint: r?.env ?? "—" },
    { label: "Episodes", value: r?.episodes ?? null, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Mean return", value: r?.mean_return ?? null, kind: "percent", digits: 2, signed: true },
    { label: "Sharpe", value: r?.sharpe ?? null, kind: "decimal", digits: 2 },
  ];

  if (!id) {
    return <PageContainer title="RL Run" subtitle="Missing :id route param.">{null}</PageContainer>;
  }

  return (
    <PageContainer
      title={r?.experiment_name ?? "RL Run"}
      subtitle={
        <span className="font-mono text-xs">
          {id}
          {r?.spec_version_hash ? ` · ${r.spec_version_hash.slice(0, 12)}` : ""}
        </span>
      }
      extra={
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => navigate("/rl")}>
            <ArrowLeft className="h-4 w-4" /> RL home
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              run.refetch();
              equity.refetch();
              reward.refetch();
              actions.refetch();
            }}
          >
            <RefreshCcw className="h-4 w-4" /> Refresh
          </Button>
        </div>
      }
    >
      <MetricsGrid metrics={metrics} columns={6} />

      <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Equity curve</CardTitle>
            <Badge variant="secondary">D3 · per episode</Badge>
          </CardHeader>
          <CardContent className="p-3">
            <EquityChart data={equityForChart} height={260} showDrawdown={false} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Reward decomposition</CardTitle>
            <Badge variant="secondary">stacked · {rewardWide.terms.length} terms</Badge>
          </CardHeader>
          <CardContent className="p-3">
            {rewardWide.rows.length === 0 ? (
              <div className="flex h-60 items-center justify-center text-sm text-[var(--text-secondary)]">
                Reward decomposition unavailable.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={rewardWide.rows} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid strokeOpacity={0.12} vertical={false} />
                  <XAxis dataKey="step" tick={{ fontSize: 10, fill: "#94A3B8" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {rewardWide.terms.map((term, i) => (
                    <Area
                      key={term}
                      dataKey={term}
                      stackId="reward"
                      stroke={REWARD_COLORS[i % REWARD_COLORS.length]}
                      fill={REWARD_COLORS[i % REWARD_COLORS.length]}
                      fillOpacity={0.35}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Action histogram</CardTitle>
          </CardHeader>
          <CardContent className="p-3">
            {actionRows.length === 0 ? (
              <div className="flex h-60 items-center justify-center text-sm text-[var(--text-secondary)]">
                Action log unavailable.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={actionRows} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
                  <CartesianGrid strokeOpacity={0.12} vertical={false} />
                  <XAxis dataKey="action" tick={{ fontSize: 10, fill: "#94A3B8" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#3B82F6" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Live progress</CardTitle>
            <Badge variant={stream.status === "open" ? "positive" : "secondary"}>{stream.status}</Badge>
          </CardHeader>
          <CardContent className="p-3">
            <ProgressTimeline events={stream.events} height={260} follow />
          </CardContent>
        </Card>
      </div>

      <p className="mt-3 text-xs text-[var(--text-secondary)]">
        Replay the run in the RL Lab via{" "}
        <Link className="text-[var(--info-fg)] underline" to={`/rl/runs/${id}/replay`}>
          /rl/runs/{id}/replay
        </Link>{" "}
        (Phase 4 deliverable). Iceberg trajectory rows are queryable via
        <code className="mx-1 rounded bg-[var(--bg-app)] px-1 font-mono">
          rl.trajectories
        </code>{" "}
        in DuckDB.
      </p>
    </PageContainer>
  );
}

const REWARD_COLORS = ["#3B82F6", "#10B981", "#F59E0B", "#A855F7", "#EF4444", "#06B6D4", "#EC4899"];
