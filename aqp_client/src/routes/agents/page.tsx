import { Activity, Bot, DollarSign, FlaskConical, Telescope } from "lucide-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useApiQuery } from "@/lib/api/hooks";
import type { AgentRunSummary, AgentSpecSummary } from "@/lib/api/agents";
import { formatTime } from "@/lib/utils";

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000;

export function AgentsHomeRoute() {
  const specs = useApiQuery<AgentSpecSummary[]>({
    queryKey: ["agents", "specs"],
    path: "/agents/specs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const runs = useApiQuery<AgentRunSummary[]>({
    queryKey: ["agents", "runs", "recent"],
    path: "/agents/runs",
    query: { limit: 25 },
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const totals = useMemo(() => {
    const list = runs.data ?? [];
    const cutoff = Date.now() - TWENTY_FOUR_HOURS_MS;
    let activeRuns = 0;
    let cost24h = 0;
    let tokens24h = 0;
    let guardrailFailures = 0;
    for (const r of list) {
      if (r.status === "running" || r.status === "queued" || r.status === "started") {
        activeRuns += 1;
      }
      const startedAt = r.started_at ? new Date(r.started_at).getTime() : 0;
      if (startedAt >= cutoff) {
        cost24h += r.cost_usd ?? 0;
        tokens24h += (r.tokens_in ?? 0) + (r.tokens_out ?? 0);
        guardrailFailures += r.guardrail_failures ?? 0;
      }
    }
    return { activeRuns, cost24h, tokens24h, guardrailFailures };
  }, [runs.data]);

  return (
    <PageContainer
      title="Agents"
      subtitle="Spec-driven agents — research, selection, trader, analysis. Each run is captured on agent_runs_v2 via AgentRuntime."
    >
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Total specs"
          icon={Bot}
          value={<Numeric value={specs.data?.length ?? null} kind="integer" digits={0} color="neutral" />}
          caption={`${(specs.data ?? []).filter((s) => s.role === "research").length} research`}
        />
        <StatCard
          title="Active runs"
          icon={Activity}
          value={<Numeric value={totals.activeRuns} kind="integer" digits={0} color={totals.activeRuns > 0 ? "force-pos" : "neutral"} />}
          caption="Running or queued"
        />
        <StatCard
          title="Spend (24h)"
          icon={DollarSign}
          value={<Numeric value={totals.cost24h} kind="money" digits={2} color="auto" />}
          caption={`${totals.tokens24h.toLocaleString()} tokens`}
        />
        <StatCard
          title="Guardrail fails (24h)"
          icon={FlaskConical}
          value={<Numeric value={totals.guardrailFailures} kind="integer" digits={0} color={totals.guardrailFailures > 0 ? "force-neg" : "force-pos"} />}
          caption="LTL / cost-cap / safety"
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent runs</CardTitle>
            <Link to="/agents/runs" className="text-xs text-[var(--info-fg)] underline">
              View all
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {(runs.data ?? []).length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-[var(--text-secondary)]">
                No runs yet.
              </div>
            ) : (
              <ul className="divide-y divide-[var(--border-subtle)]">
                {(runs.data ?? []).slice(0, 10).map((r) => (
                  <li key={r.id} className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-4 py-2 text-sm">
                    <Link to={`/agents/runs/${r.id}`} className="flex flex-col">
                      <span className="font-medium">{r.spec_name ?? "—"}</span>
                      <span className="font-mono text-[10px] text-[var(--text-muted)]">{r.id}</span>
                    </Link>
                    <Badge
                      variant={
                        r.status === "ok" || r.status === "completed"
                          ? "positive"
                          : r.status === "error" || r.status === "failed"
                            ? "negative"
                            : r.status === "running" || r.status === "queued"
                              ? "default"
                              : "secondary"
                      }
                    >
                      {r.status ?? "—"}
                    </Badge>
                    <Numeric
                      value={r.cost_usd ?? null}
                      kind="money"
                      digits={3}
                      color="neutral"
                      className="text-right"
                    />
                    <span className="text-right text-xs text-[var(--text-secondary)]">
                      {r.started_at ? formatTime(r.started_at) : "—"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick links</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1.5 text-sm">
            <Link to="/agents/registry" className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-[var(--bg-elevated)]">
              <Telescope className="h-4 w-4 text-[var(--info-fg)]" /> Agent Registry
            </Link>
            <Link to="/agents/runs" className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-[var(--bg-elevated)]">
              <Activity className="h-4 w-4 text-[var(--info-fg)]" /> Agent Runs
            </Link>
            <Link to="/action-center" className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-[var(--bg-elevated)]">
              <Bot className="h-4 w-4 text-[var(--info-fg)]" /> Action Center
            </Link>
            <Separator />
            <Link to="/agents/templates" className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]">
              Agent Templates (Phase 3)
            </Link>
            <Link to="/agents/evaluations" className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]">
              Evaluations (Phase 3)
            </Link>
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}

interface StatCardProps {
  title: string;
  icon: typeof Activity;
  value: React.ReactNode;
  caption: string;
}

function StatCard({ title, icon: Icon, value, caption }: StatCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-[var(--text-secondary)]" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold">{value}</div>
        <div className="mt-1 text-xs text-[var(--text-secondary)]">{caption}</div>
      </CardContent>
    </Card>
  );
}
