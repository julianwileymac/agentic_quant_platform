import { Component, type ErrorInfo, type ReactNode, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { PageContainer } from "@/components/shell/PageContainer";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import {
  type InfraStatus,
  type QueueDepths,
  type PipelineStatus,
  type SecretsStatus,
  type K8sNamespacePods,
  infraApi,
} from "@/lib/api/infra";
import { terraformApi, type TerraformWorkspace, type TerraformRun } from "@/lib/api/terraform";
import { apiFetch } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// Pane-scoped error boundary — keeps a render crash in one pane from
// bubbling up to the route-level `errorElement: <NotFoundRoute />`, which
// would otherwise show the "route does not exist" placeholder for the
// entire InfraRoute.
// ---------------------------------------------------------------------------

class PaneErrorBoundary extends Component<
  { name: string; children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error(`[/infra] pane "${this.props.name}" crashed:`, error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="rounded border border-[var(--neg-border,#dc2626)] bg-[var(--bg-card)] p-3 text-xs text-[var(--neg-fg)]">
          <p className="mb-1 font-semibold">Pane "{this.props.name}" failed to render.</p>
          <pre className="whitespace-pre-wrap font-mono">{this.state.error.message}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

const POLL_MS_FAST = 5_000;
const POLL_MS_MED = 15_000;
const NAMESPACES = ["aqp-system", "aqp-local", "aqp-paper", "aqp-live", "aqp-backtest", "aqp-agents"];

/**
 * /infra — Infrastructure Overview shell.
 *
 * Hosts the 7 panes the plan specifies:
 *   A. Infrastructure Overview
 *   B. Bot Fleet Control
 *   C. Celery Queue Monitor
 *   D. Data Pipeline Status
 *   E. Secrets Sync Status
 *   F. K8s Resource Explorer
 *   G. Canary Deployment Controller
 *
 * Tabs are URL-synced via ?tab=<pane> so deep links work from the
 * topbar / kill-switch flow.
 */
export function InfraRoute() {
  const [search, setSearch] = useSearchParams();
  const activeTab = search.get("tab") || "overview";
  const setTab = (tab: string) => {
    const next = new URLSearchParams(search);
    next.set("tab", tab);
    setSearch(next, { replace: true });
  };

  return (
    <PageContainer
      title="Infrastructure"
      subtitle="Terraform-driven IaC control plane — workspaces, queues, pipelines, secrets, k8s, canary"
    >
      <Tabs value={activeTab} onValueChange={setTab}>
        <TabsList className="mb-4 flex flex-wrap gap-1">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="bots">Bots</TabsTrigger>
          <TabsTrigger value="queues">Queues</TabsTrigger>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="secrets">Secrets</TabsTrigger>
          <TabsTrigger value="k8s">K8s Explorer</TabsTrigger>
          <TabsTrigger value="canary">Canary</TabsTrigger>
          <TabsTrigger value="terraform">Terraform</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <PaneErrorBoundary name="overview"><OverviewPane /></PaneErrorBoundary>
        </TabsContent>
        <TabsContent value="bots">
          <PaneErrorBoundary name="bots"><BotsPane /></PaneErrorBoundary>
        </TabsContent>
        <TabsContent value="queues">
          <PaneErrorBoundary name="queues"><QueuesPane /></PaneErrorBoundary>
        </TabsContent>
        <TabsContent value="pipeline">
          <PaneErrorBoundary name="pipeline"><PipelinePane /></PaneErrorBoundary>
        </TabsContent>
        <TabsContent value="secrets">
          <PaneErrorBoundary name="secrets"><SecretsPane /></PaneErrorBoundary>
        </TabsContent>
        <TabsContent value="k8s">
          <PaneErrorBoundary name="k8s"><K8sExplorerPane /></PaneErrorBoundary>
        </TabsContent>
        <TabsContent value="canary">
          <PaneErrorBoundary name="canary"><CanaryPane /></PaneErrorBoundary>
        </TabsContent>
        <TabsContent value="terraform">
          <PaneErrorBoundary name="terraform"><TerraformPane /></PaneErrorBoundary>
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}

// ---------------------------------------------------------------------------
// Shared helper hook — light polling
// ---------------------------------------------------------------------------

function usePolling<T>(
  loader: () => Promise<T>,
  intervalMs: number,
  deps: ReadonlyArray<unknown> = [],
): { data: T | null; error: string | null; refresh: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      loader()
        .then((d) => {
          if (!cancelled) {
            setData(d);
            setError(null);
          }
        })
        .catch((e) => {
          if (!cancelled) setError(e instanceof Error ? e.message : String(e));
        });
    load();
    const t = setInterval(load, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, tick, ...deps]);

  return { data, error, refresh: () => setTick((n) => n + 1) };
}

// ---------------------------------------------------------------------------
// Pane A — Overview
// ---------------------------------------------------------------------------

function OverviewPane() {
  const { data, error } = usePolling<InfraStatus>(() => infraApi.status(), POLL_MS_MED);
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Skeleton />;

  // Defensive defaults — the backend may add / rename keys; never crash
  // the pane just because a counter is missing.
  const workspaces = Array.isArray(data.workspaces) ? data.workspaces : [];
  const totals = data.totals ?? { workspaces: 0, runs: 0, drift_alert: false };
  const driftCount = workspaces.filter((w) => w.drift).length;
  const erroredCount = workspaces.filter(
    (w) => w.last_run_status === "errored" || w.last_run_status === "policy_failed",
  ).length;
  const cleanCount = workspaces.filter(
    (w) => w.last_run_status === "completed" && !w.drift,
  ).length;
  return (
    <div className="space-y-4">
      <section className="grid grid-cols-1 gap-2 sm:grid-cols-4">
        <SummaryCard label="Workspaces" value={totals.workspaces} tone="info" />
        <SummaryCard label="Clean" value={cleanCount} tone="pos" />
        <SummaryCard label="Drifting" value={driftCount} tone="warn" />
        <SummaryCard label="Errored" value={erroredCount} tone="neg" />
      </section>
      <section>
        <h3 className="mb-2 text-xs uppercase tracking-wide text-[var(--text-secondary)]">
          Workspaces
        </h3>
        <DataTable
          rows={workspaces.map((w) => ({
            slug: w.slug,
            environment: w.environment,
            state_backend: w.state_backend,
            last_run_kind: w.last_run_kind ?? "—",
            last_run_status: w.last_run_status ?? "—",
            state_serial: w.state_serial ?? "—",
            resource_count: w.resource_count ?? "—",
            drift: w.drift ? "yes" : "no",
          }))}
          columns={[
            { key: "slug", label: "Slug" },
            { key: "environment", label: "Env" },
            { key: "state_backend", label: "Backend" },
            { key: "last_run_kind", label: "Last kind" },
            { key: "last_run_status", label: "Last status" },
            { key: "state_serial", label: "State serial" },
            { key: "resource_count", label: "Resources" },
            { key: "drift", label: "Drift" },
          ]}
        />
      </section>
      <p className="text-[10px] text-[var(--text-muted)]">
        Generated {data.generated_at ?? "—"} · {totals.runs} run(s) ·{" "}
        {totals.drift_alert ? "drift alert active" : "no drift alerts"}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pane B — Bots
// ---------------------------------------------------------------------------

function BotsPane() {
  const { data, error, refresh } = usePolling<{ items: Array<Record<string, unknown>> }>(
    () => apiFetch<{ items: Array<Record<string, unknown>> }>("/bots"),
    POLL_MS_MED,
  );
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Skeleton />;
  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--text-secondary)]">
        Live bot fleet. Use the topbar Halt button to halt every deployment at once.
      </p>
      <DataTable
        rows={data.items as Array<Record<string, unknown>>}
        columns={[
          { key: "slug", label: "Slug" },
          { key: "name", label: "Name" },
          { key: "kind", label: "Kind" },
          { key: "status", label: "Status" },
          { key: "current_version", label: "Version" },
        ]}
      />
      <Button size="sm" variant="ghost" onClick={refresh}>Refresh</Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pane C — Queues
// ---------------------------------------------------------------------------

function QueuesPane() {
  const { data, error } = usePolling<QueueDepths>(() => infraApi.queues(), POLL_MS_FAST);
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Skeleton />;
  const queueRows = (data.queues ?? []).map((q) => ({
    name: q.name,
    depth: q.depth ?? 0,
    replicas: q.current_replicas ?? "—",
  }));
  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--text-secondary)]">
        Celery queue depths (Redis LLEN) + KEDA replica counts. Polling every 5s.
      </p>
      <DataTable
        rows={queueRows}
        columns={[
          { key: "name", label: "Queue" },
          { key: "depth", label: "Depth" },
          { key: "replicas", label: "Replicas" },
        ]}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pane D — Pipeline
// ---------------------------------------------------------------------------

function PipelinePane() {
  const { data, error } = usePolling<PipelineStatus>(() => infraApi.pipeline(), POLL_MS_MED);
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Skeleton />;
  return (
    <div className="space-y-4">
      <section>
        <h3 className="mb-2 text-xs uppercase tracking-wide text-[var(--text-secondary)]">
          Alembic head
        </h3>
        <code className="font-mono text-sm">{data.alembic_revision ?? "—"}</code>
      </section>
      <section>
        <h3 className="mb-2 text-xs uppercase tracking-wide text-[var(--text-secondary)]">
          Parquet lake
        </h3>
        <p className="font-mono text-xs">
          manifests: {data.parquet?.manifest_count ?? 0} · pipeline_runs:{" "}
          {data.parquet?.pipeline_run_count ?? 0}
        </p>
      </section>
      <section>
        <h3 className="mb-2 text-xs uppercase tracking-wide text-[var(--text-secondary)]">
          Ingestion adapters
        </h3>
        <DataTable
          rows={(data.adapters ?? []).map((a) => ({
            name: a.name,
            last_run_at: a.last_run_at ?? "—",
            runs_recent: a.runs_recent ?? 0,
            status: a.status ?? "—",
          }))}
          columns={[
            { key: "name", label: "Adapter" },
            { key: "last_run_at", label: "Last run" },
            { key: "runs_recent", label: "Recent runs" },
            { key: "status", label: "Status" },
          ]}
        />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pane E — Secrets sync
// ---------------------------------------------------------------------------

function SecretsPane() {
  const { data, error } = usePolling<SecretsStatus>(() => infraApi.secrets(), POLL_MS_MED);
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <Skeleton />;
  return (
    <div className="space-y-3">
      <p className="text-xs text-[var(--text-secondary)]">
        Credential resolver chain (in priority order). Values are NEVER shown — only metadata.
      </p>
      <DataTable
        rows={(data.stores ?? []).map((s) => ({
          alias: s.alias,
          kind: s.kind,
          priority: s.priority,
        }))}
        columns={[
          { key: "alias", label: "Store" },
          { key: "kind", label: "Kind" },
          { key: "priority", label: "Priority" },
        ]}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pane F — K8s explorer
// ---------------------------------------------------------------------------

function K8sExplorerPane() {
  const [ns, setNs] = useState<string>(NAMESPACES[0] ?? "aqp-system");
  const { data, error } = usePolling<K8sNamespacePods>(
    () => infraApi.k8sNamespace(ns),
    POLL_MS_MED,
    [ns],
  );
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label className="text-xs text-[var(--text-secondary)]">Namespace</label>
        <select
          className="rounded border border-[var(--border-default)] bg-[var(--bg-card)] px-2 py-1 text-xs"
          value={ns}
          onChange={(e) => setNs(e.target.value)}
        >
          {NAMESPACES.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
        {data && !data.adapter_available ? (
          <span className="text-[10px] text-[var(--warn-fg)]">
            (no Kubernetes adapter active — running in local Docker mode)
          </span>
        ) : null}
      </div>
      {error ? <ErrorBanner message={error} /> : !data ? <Skeleton /> : (
        <DataTable
          rows={(data.pods ?? []).map((p) => ({
            name: p.name,
            phase: p.phase ?? "—",
            node: p.node ?? "—",
            pod_ip: p.pod_ip ?? "—",
            started_at: p.started_at ?? "—",
          }))}
          columns={[
            { key: "name", label: "Pod" },
            { key: "phase", label: "Phase" },
            { key: "node", label: "Node" },
            { key: "pod_ip", label: "IP" },
            { key: "started_at", label: "Started" },
          ]}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pane G — Canary controller
// ---------------------------------------------------------------------------

function CanaryPane() {
  const [weight, setWeight] = useState(100);
  const [pending, setPending] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [last, setLast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applyWeight = async (w: number) => {
    setPending(true);
    setError(null);
    try {
      const result = await infraApi.canarySet({ weight: w });
      setLast(`Set to ${result.weight}% (cm=${result.config_map_name} ns=${result.namespace})`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--text-secondary)]">
        Canary traffic weight between legacy Solara (left) and the active Vite frontend (right).
        Drag to set; click "Apply" to push to the ingress ConfigMap.
      </p>
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={0}
          max={100}
          value={weight}
          onChange={(e) => setWeight(Number(e.target.value))}
          className="flex-1"
        />
        <span className="font-mono text-sm">{weight}%</span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded border border-[var(--border-default)] bg-[var(--bg-card)]">
        <div
          className="h-full bg-[var(--accent-fg)] transition-all"
          style={{ width: `${weight}%` }}
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" disabled={pending} onClick={() => applyWeight(weight)}>
          Apply
        </Button>
        <Button
          size="sm"
          variant="destructive"
          disabled={pending}
          onClick={() => setConfirmOpen(true)}
        >
          Complete cutover (100%)
        </Button>
      </div>
      {last && <p className="text-xs text-[var(--pos-fg)]">{last}</p>}
      {error && <ErrorBanner message={error} />}
      <ConfirmFrictionDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Complete Vite frontend cutover"
        consequence="This sets 100% of traffic to the Vite frontend. The legacy Solara UI becomes inaccessible until you manually rebalance."
        confirmPhrase="CUTOVER"
        confirmLabel="Complete cutover"
        confirmVariant="destructive"
        onConfirm={() => applyWeight(100)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pane (extra) — Terraform overview embedded inline so operators don't have
// to leave the /infra surface to see workspace+run health at a glance.
// ---------------------------------------------------------------------------

function TerraformPane() {
  const { data: wsData } = usePolling<{ items: TerraformWorkspace[] }>(
    () => terraformApi.listWorkspaces(),
    POLL_MS_MED,
  );
  const { data: runData } = usePolling<{ items: TerraformRun[] }>(
    () => terraformApi.listRuns({ limit: 25 }),
    POLL_MS_FAST,
  );
  const navigate = useNavigate();
  return (
    <div className="space-y-4">
      <section>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-xs uppercase tracking-wide text-[var(--text-secondary)]">
            Workspaces
          </h3>
          <Button size="sm" variant="ghost" onClick={() => navigate("/infra/terraform")}>
            Open Terraform IDE
          </Button>
        </div>
        <DataTable
          rows={(wsData?.items ?? []).map((w) => ({
            slug: w.slug,
            environment: w.environment,
            backend: w.state_backend,
            tenant: w.tenant_org_id ?? "—",
            archived: w.archived ? "yes" : "no",
          }))}
          columns={[
            { key: "slug", label: "Slug" },
            { key: "environment", label: "Env" },
            { key: "backend", label: "Backend" },
            { key: "tenant", label: "Tenant org" },
            { key: "archived", label: "Archived" },
          ]}
        />
      </section>
      <section>
        <h3 className="mb-2 text-xs uppercase tracking-wide text-[var(--text-secondary)]">
          Recent runs
        </h3>
        <DataTable
          rows={(runData?.items ?? []).map((r) => ({
            id: r.id.slice(0, 8),
            kind: r.run_kind,
            status: r.status,
            started: r.started_at?.slice(0, 19) ?? "—",
            exit: r.exit_code ?? "—",
          }))}
          columns={[
            { key: "id", label: "Run" },
            { key: "kind", label: "Kind" },
            { key: "status", label: "Status" },
            { key: "started", label: "Started" },
            { key: "exit", label: "Exit" },
          ]}
        />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared UI helpers
// ---------------------------------------------------------------------------

function Skeleton() {
  return <p className="text-xs text-[var(--text-secondary)]">Loading…</p>;
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded border border-[var(--neg-border,#dc2626)] bg-[var(--bg-card)] p-3 text-xs text-[var(--neg-fg)]">
      {message}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone: "info" | "warn" | "neg" | "pos";
}) {
  const colorVar = {
    info: "var(--text-primary)",
    warn: "var(--warn-fg)",
    neg: "var(--neg-fg)",
    pos: "var(--pos-fg)",
  }[tone];
  return (
    <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-card)] p-3">
      <p className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)]">{label}</p>
      <p
        className="mt-1 text-base font-semibold"
        style={{ color: colorVar, fontVariantNumeric: "tabular-nums" }}
      >
        {value}
      </p>
    </div>
  );
}

function DataTable<R extends Record<string, unknown>>({
  rows,
  columns,
}: {
  rows: R[];
  columns: { key: string; label: string }[];
}) {
  if (rows.length === 0) {
    return <p className="text-xs text-[var(--text-secondary)]">No rows.</p>;
  }
  return (
    <div className="overflow-x-auto rounded border border-[var(--border-default)]">
      <table className="w-full text-xs">
        <thead className="bg-[var(--bg-card)]">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className="px-2 py-1 text-left font-semibold text-[var(--text-secondary)]"
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={idx}
              className="border-t border-[var(--border-default)] hover:bg-[var(--bg-hover)]"
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className="px-2 py-1 font-mono"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {String(row[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default InfraRoute;
