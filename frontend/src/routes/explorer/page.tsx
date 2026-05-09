import {
  AppWindow,
  Bot,
  Database,
  FlaskConical,
  LineChart,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";

import { DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApiQuery } from "@/lib/api/hooks";
import type {
  LabCorpus,
  LabMemoryEntry,
  ProjectAgent,
  ProjectAgentRun,
  ProjectBacktest,
  ProjectStrategy,
} from "@/lib/api/tenancy";
import { cn, formatTime } from "@/lib/utils";
import { useTenancyStore } from "@/store/tenancy";

type Filter = "strategies" | "backtests" | "agents" | "agent-runs" | "corpora" | "memory";

interface FilterTab {
  value: Filter;
  label: string;
  icon: LucideIcon;
  scope: "project" | "lab";
}

const FILTERS: FilterTab[] = [
  { value: "strategies", label: "Strategies", icon: AppWindow, scope: "project" },
  { value: "backtests", label: "Backtests", icon: LineChart, scope: "project" },
  { value: "agents", label: "Agents", icon: Bot, scope: "project" },
  { value: "agent-runs", label: "Agent Runs", icon: Bot, scope: "project" },
  { value: "corpora", label: "RAG Corpora", icon: Database, scope: "lab" },
  { value: "memory", label: "Memory", icon: Sparkles, scope: "lab" },
];

export function ResourceExplorerRoute() {
  const projectId = useTenancyStore((s) => s.projectId);
  const labId = useTenancyStore((s) => s.labId);
  const [filter, setFilter] = useState<Filter>("strategies");

  const activeTab = FILTERS.find((f) => f.value === filter)!;
  const scopeId = activeTab.scope === "project" ? projectId : labId;
  const scopeKind = activeTab.scope;

  const strategies = useApiQuery<ProjectStrategy[]>({
    queryKey: ["explorer", "strategies", projectId],
    path: `/projects/${encodeURIComponent(projectId ?? "")}/strategies`,
    enabled: filter === "strategies" && Boolean(projectId),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const backtests = useApiQuery<ProjectBacktest[]>({
    queryKey: ["explorer", "backtests", projectId],
    path: `/projects/${encodeURIComponent(projectId ?? "")}/backtests`,
    enabled: filter === "backtests" && Boolean(projectId),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const agents = useApiQuery<ProjectAgent[]>({
    queryKey: ["explorer", "agents", projectId],
    path: `/projects/${encodeURIComponent(projectId ?? "")}/agents`,
    enabled: filter === "agents" && Boolean(projectId),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const runs = useApiQuery<ProjectAgentRun[]>({
    queryKey: ["explorer", "agent-runs", projectId],
    path: `/projects/${encodeURIComponent(projectId ?? "")}/runs`,
    enabled: filter === "agent-runs" && Boolean(projectId),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const corpora = useApiQuery<LabCorpus[]>({
    queryKey: ["explorer", "corpora", labId],
    path: `/labs/${encodeURIComponent(labId ?? "")}/corpora`,
    enabled: filter === "corpora" && Boolean(labId),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const memory = useApiQuery<LabMemoryEntry[]>({
    queryKey: ["explorer", "memory", labId],
    path: `/labs/${encodeURIComponent(labId ?? "")}/memory`,
    enabled: filter === "memory" && Boolean(labId),
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const counts = useMemo(
    () => ({
      strategies: strategies.data?.length ?? 0,
      backtests: backtests.data?.length ?? 0,
      agents: agents.data?.length ?? 0,
      runs: runs.data?.length ?? 0,
      corpora: corpora.data?.length ?? 0,
      memory: memory.data?.length ?? 0,
    }),
    [strategies.data, backtests.data, agents.data, runs.data, corpora.data, memory.data],
  );

  const metrics: Metric[] = [
    { label: "Project", value: null, hint: <span className="font-mono">{projectId ?? "—"}</span> },
    { label: "Lab", value: null, hint: <span className="font-mono">{labId ?? "—"}</span> },
    { label: "Strategies", value: counts.strategies, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Backtests", value: counts.backtests, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Agents", value: counts.agents, kind: "integer", digits: 0, tone: "neutral" },
    { label: "Runs", value: counts.runs, kind: "integer", digits: 0, tone: "neutral" },
  ];

  return (
    <PageContainer
      title="Resource Explorer"
      subtitle="Project- and lab-scoped resources for the active tenancy. Switch tenancy from the topbar to view a different project / lab."
    >
      <MetricsGrid metrics={metrics} columns={6} />

      <div className="mt-3 flex flex-wrap gap-2">
        {FILTERS.map((tab) => {
          const Icon = tab.icon;
          const active = tab.value === filter;
          const disabled = !(tab.scope === "project" ? projectId : labId);
          return (
            <Button
              key={tab.value}
              variant={active ? "default" : "outline"}
              size="sm"
              onClick={() => setFilter(tab.value)}
              disabled={disabled}
              className="gap-2"
            >
              <Icon className="h-3.5 w-3.5" />
              {tab.label}
              <Badge variant="secondary" className="text-[10px]">
                {counts[tab.value === "agent-runs" ? "runs" : tab.value]}
              </Badge>
            </Button>
          );
        })}
      </div>

      <Card className="mt-3 h-[calc(100vh-340px)]">
        <CardContent className="h-full p-0">
          {!scopeId ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-[var(--text-secondary)]">
              <FlaskConical className="h-6 w-6" />
              <span className={cn("text-xs")}>
                Active {scopeKind} not set. Choose one from the topbar.
              </span>
            </div>
          ) : filter === "strategies" ? (
            <DataTable<ProjectStrategy>
              rows={strategies.data ?? []}
              rowKey={(s) => s.id}
              columns={[
                { key: "name", header: "Strategy", render: (s) => <span className="font-medium">{s.name}</span> },
                {
                  key: "version",
                  header: "Version",
                  width: 100,
                  align: "right",
                  render: (s) => <Numeric value={s.version} kind="integer" digits={0} color="neutral" />,
                },
                {
                  key: "status",
                  header: "Status",
                  width: 110,
                  render: (s) => <Badge variant="secondary">{s.status}</Badge>,
                },
              ]}
            />
          ) : filter === "backtests" ? (
            <DataTable<ProjectBacktest>
              rows={backtests.data ?? []}
              rowKey={(b) => b.id}
              columns={[
                {
                  key: "id",
                  header: "Run",
                  render: (b) => <span className="font-mono text-xs">{b.id}</span>,
                },
                {
                  key: "status",
                  header: "Status",
                  width: 110,
                  render: (b) => <Badge variant="secondary">{b.status}</Badge>,
                },
                {
                  key: "sharpe",
                  header: "Sharpe",
                  width: 100,
                  align: "right",
                  render: (b) => <Numeric value={b.sharpe ?? null} kind="decimal" digits={2} color="auto" />,
                },
                {
                  key: "total_return",
                  header: "Total return",
                  width: 130,
                  align: "right",
                  render: (b) => (
                    <Numeric value={b.total_return ?? null} kind="percent" digits={2} color="auto" signed />
                  ),
                },
                {
                  key: "created_at",
                  header: "Created",
                  width: 140,
                  align: "right",
                  render: (b) => (
                    <span className="text-[var(--text-secondary)]">
                      {b.created_at ? formatTime(b.created_at) : "—"}
                    </span>
                  ),
                },
              ]}
            />
          ) : filter === "agents" ? (
            <DataTable<ProjectAgent>
              rows={agents.data ?? []}
              rowKey={(a) => a.id}
              columns={[
                { key: "name", header: "Agent", render: (a) => <span className="font-medium">{a.name}</span> },
                { key: "role", header: "Role", width: 130, render: (a) => <Badge variant="secondary">{a.role}</Badge> },
                {
                  key: "version",
                  header: "Version",
                  width: 100,
                  align: "right",
                  render: (a) => <Numeric value={a.current_version} kind="integer" digits={0} color="neutral" />,
                },
              ]}
            />
          ) : filter === "agent-runs" ? (
            <DataTable<ProjectAgentRun>
              rows={runs.data ?? []}
              rowKey={(r) => r.id}
              columns={[
                {
                  key: "spec_name",
                  header: "Spec",
                  render: (r) => <span className="font-mono text-xs">{r.spec_name}</span>,
                },
                {
                  key: "status",
                  header: "Status",
                  width: 110,
                  render: (r) => <Badge variant="secondary">{r.status}</Badge>,
                },
                {
                  key: "cost",
                  header: "Cost",
                  width: 110,
                  align: "right",
                  render: (r) => <Numeric value={r.cost_usd ?? null} kind="money" digits={3} color="auto" />,
                },
                {
                  key: "started",
                  header: "Started",
                  width: 140,
                  align: "right",
                  render: (r) => (
                    <span className="text-[var(--text-secondary)]">
                      {r.started_at ? formatTime(r.started_at) : "—"}
                    </span>
                  ),
                },
              ]}
            />
          ) : filter === "corpora" ? (
            <DataTable<LabCorpus>
              rows={corpora.data ?? []}
              rowKey={(c) => c.id}
              columns={[
                { key: "name", header: "Corpus", render: (c) => <span className="font-mono">{c.name}</span> },
                { key: "order", header: "Order", width: 100, render: (c) => <Badge variant="secondary">{c.order}</Badge> },
                {
                  key: "l1l2",
                  header: "L1 / L2",
                  width: 200,
                  render: (c) => (
                    <span className="font-mono text-xs">
                      {c.l1} / {c.l2}
                    </span>
                  ),
                },
                {
                  key: "chunks",
                  header: "Chunks",
                  width: 110,
                  align: "right",
                  render: (c) => <Numeric value={c.chunks_count} kind="integer" digits={0} color="neutral" />,
                },
              ]}
            />
          ) : (
            <DataTable<LabMemoryEntry>
              rows={memory.data ?? []}
              rowKey={(m) => m.id}
              columns={[
                { key: "role", header: "Role", width: 110, render: (m) => <Badge variant="secondary">{m.role}</Badge> },
                {
                  key: "vt_symbol",
                  header: "Symbol",
                  width: 130,
                  render: (m) => <span className="font-mono text-xs">{m.vt_symbol ?? "—"}</span>,
                },
                {
                  key: "situation",
                  header: "Situation",
                  render: (m) => <span className="text-xs italic">{m.situation}</span>,
                },
                {
                  key: "lesson",
                  header: "Lesson",
                  render: (m) => <span className="text-xs">{m.lesson}</span>,
                },
                {
                  key: "created_at",
                  header: "Created",
                  width: 130,
                  align: "right",
                  render: (m) => (
                    <span className="text-[var(--text-secondary)]">
                      {m.created_at ? formatTime(m.created_at) : "—"}
                    </span>
                  ),
                },
              ]}
            />
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
