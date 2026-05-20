import {
  ArrowLeft,
  CloudUpload,
  FlaskConical,
  PlayCircle,
  Power,
  RefreshCcw,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { MetricsGrid, type Metric } from "@/components/common/MetricsGrid";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { BotsApi, type BotDeploymentOut, type BotDetail, type BotVersionOut } from "@/lib/api/bots";
import { formatTime } from "@/lib/utils";
import { useTenancyStore } from "@/store/tenancy";

import { BotChatPanel } from "./BotChatPanel";

type FrictionAction = "halt" | "backtest" | "paper" | "deploy" | null;

const FRICTION_LABEL: Record<Exclude<FrictionAction, null>, string> = {
  halt: "Halt bot",
  backtest: "Run backtest",
  paper: "Start paper",
  deploy: "Deploy bot",
};

export function BotDetailRoute() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const mode = useTenancyStore((s) => s.mode);
  const [friction, setFriction] = useState<FrictionAction>(null);

  const bot = useApiQuery<BotDetail>({
    queryKey: ["bot", id],
    path: `/bots/${encodeURIComponent(id ?? "")}`,
    enabled: Boolean(id),
  });
  const versions = useApiQuery<BotVersionOut[]>({
    queryKey: ["bot", id, "versions"],
    path: `/bots/${encodeURIComponent(id ?? "")}/versions`,
    enabled: Boolean(id && bot.data),
  });
  const deployments = useApiQuery<BotDeploymentOut[]>({
    queryKey: ["bot", id, "deployments"],
    path: `/bots/${encodeURIComponent(id ?? "")}/deployments`,
    enabled: Boolean(id && bot.data),
    refetchInterval: 5_000,
  });

  const metrics = useMemo<Metric[]>(() => {
    const data = bot.data;
    if (!data) return [];
    const summary = (data.spec as { summary?: Record<string, number> } | undefined)?.summary ?? {};
    return [
      { label: "Status", value: null, hint: <Badge variant="secondary">{data.status ?? "—"}</Badge> },
      { label: "Total PnL", value: data.pnl_total ?? null, kind: "money", digits: 0, signed: true },
      { label: "Sharpe", value: data.sharpe ?? null, kind: "decimal", digits: 2 },
      { label: "Annotations", value: null, hint: (data.annotations ?? []).join(" · ") || "—" },
      { label: "Version", value: data.current_version ?? null, kind: "integer", digits: 0, tone: "neutral" },
      {
        label: "Strategy",
        value: null,
        hint: <span className="font-mono text-xs">{(summary.strategy as unknown as string) ?? data.strategy ?? "—"}</span>,
      },
    ];
  }, [bot.data]);

  if (!id) {
    return <PageContainer title="Bot" subtitle="Missing :id route param.">{null}</PageContainer>;
  }
  if (bot.isLoading) {
    return <PageContainer title="Bot" subtitle="Loading…">{null}</PageContainer>;
  }
  if (bot.error || !bot.data) {
    return (
      <PageContainer title="Bot" subtitle={`Failed to load bot ${id}.`}>
        <Card>
          <CardContent>
            <p className="text-sm text-[var(--neg-fg)]">{bot.error?.message ?? "Bot not found"}</p>
            <Button variant="outline" size="sm" onClick={() => navigate("/bots")} className="mt-3">
              <ArrowLeft className="h-4 w-4" /> Back to Bots
            </Button>
          </CardContent>
        </Card>
      </PageContainer>
    );
  }

  const data = bot.data;

  const submit = async () => {
    if (!friction) return;
    try {
      switch (friction) {
        case "halt":
          await BotsApi.halt(id);
          toast.success(`${data.name} halted`);
          break;
        case "backtest":
          await BotsApi.backtest(id);
          toast.success("Backtest queued");
          break;
        case "paper":
          await BotsApi.startPaper(id);
          toast.success("Paper run queued");
          break;
        case "deploy":
          await BotsApi.deploy(id);
          toast.success("Deploy queued");
          break;
      }
      bot.refetch();
      deployments.refetch();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`${FRICTION_LABEL[friction]} failed: ${msg}`);
      throw err;
    }
  };

  const headerExtra = (
    <div className="flex items-center gap-2">
      <Button variant="ghost" size="sm" onClick={() => bot.refetch()}>
        <RefreshCcw className="h-4 w-4" /> Refresh
      </Button>
      <Button variant="outline" size="sm" onClick={() => setFriction("backtest")}>
        <FlaskConical className="h-4 w-4" /> Run backtest
      </Button>
      <Button variant="outline" size="sm" onClick={() => setFriction("paper")}>
        <PlayCircle className="h-4 w-4" /> Start paper
      </Button>
      <Button variant="warn" size="sm" onClick={() => setFriction("deploy")}>
        <CloudUpload className="h-4 w-4" /> Deploy
      </Button>
      <Button variant="destructive" size="sm" onClick={() => setFriction("halt")}>
        <Power className="h-4 w-4" /> Halt
      </Button>
    </div>
  );

  return (
    <PageContainer
      title={data.name}
      subtitle={
        <span className="font-mono text-xs">
          {data.id} · {data.kind}
          {data.description ? ` · ${data.description}` : ""}
        </span>
      }
      extra={headerExtra}
    >
      <MetricsGrid metrics={metrics} columns={6} />

      <Tabs defaultValue="overview" className="mt-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="versions">Versions ({versions.data?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="deployments">Deployments ({deployments.data?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="runs">Runs</TabsTrigger>
          {data.kind === "research" ? <TabsTrigger value="chat">Chat</TabsTrigger> : null}
        </TabsList>

        <TabsContent value="overview">
          <Card>
            <CardHeader>
              <CardTitle>Spec</CardTitle>
              <Badge variant="secondary">hash-locked, immutable</Badge>
            </CardHeader>
            <CardContent>
              <ScrollArea className="max-h-[60vh]">
                <pre className="whitespace-pre-wrap break-words font-mono text-xs text-[var(--text-primary)]">
                  {JSON.stringify(data.spec ?? {}, null, 2)}
                </pre>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="versions">
          <Card>
            <CardContent className="p-0">
              <div className="h-[60vh]">
                <DataTable<BotVersionOut>
                  rows={versions.data ?? []}
                  rowKey={(v) => v.id}
                  emptyState={<span>No versions yet.</span>}
                  columns={[
                    {
                      key: "version",
                      header: "Version",
                      width: 80,
                      align: "right",
                      render: (v) => <Numeric value={v.version} kind="integer" digits={0} color="neutral" />,
                    },
                    {
                      key: "hash",
                      header: "Spec hash",
                      width: 200,
                      render: (v) => (
                        <span className="font-mono text-xs">{v.spec_hash.slice(0, 18)}…</span>
                      ),
                    },
                    {
                      key: "notes",
                      header: "Notes",
                      render: (v) => <span className="text-xs">{v.notes ?? "—"}</span>,
                    },
                    {
                      key: "created_at",
                      header: "Created",
                      width: 160,
                      align: "right",
                      render: (v) => (
                        <span className="text-[var(--text-secondary)]">{formatTime(v.created_at)}</span>
                      ),
                    },
                  ]}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="deployments">
          <Card>
            <CardContent className="p-0">
              <div className="h-[60vh]">
                <DataTable<BotDeploymentOut>
                  rows={deployments.data ?? []}
                  rowKey={(d) => d.id}
                  emptyState={<span>No deployments yet.</span>}
                  columns={[
                    {
                      key: "target",
                      header: "Target",
                      width: 160,
                      render: (d) => <Badge variant="secondary">{d.target}</Badge>,
                    },
                    {
                      key: "status",
                      header: "Status",
                      width: 110,
                      render: (d) => (
                        <Badge
                          variant={
                            d.status === "running"
                              ? "positive"
                              : d.status === "failed"
                                ? "negative"
                                : d.status === "halted"
                                  ? "warn"
                                  : "secondary"
                          }
                        >
                          {d.status}
                        </Badge>
                      ),
                    },
                    {
                      key: "task_id",
                      header: "Task",
                      width: 220,
                      render: (d) => (
                        <span className="font-mono text-xs">{d.task_id ?? "—"}</span>
                      ),
                    },
                    {
                      key: "started_at",
                      header: "Started",
                      width: 160,
                      align: "right",
                      render: (d) => (
                        <span className="text-[var(--text-secondary)]">{formatTime(d.started_at)}</span>
                      ),
                    },
                    {
                      key: "ended_at",
                      header: "Ended",
                      width: 160,
                      align: "right",
                      render: (d) => (
                        <span className="text-[var(--text-secondary)]">
                          {d.ended_at ? formatTime(d.ended_at) : "—"}
                        </span>
                      ),
                    },
                  ]}
                />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="runs">
          <Card>
            <CardHeader>
              <CardTitle>Backtests + paper sessions</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-[var(--text-secondary)]">
              <p>
                Bot-scoped backtests live under{" "}
                <Link to="/backtest" className="text-[var(--info-fg)] underline">
                  Backtests
                </Link>
                ; paper sessions under{" "}
                <Link to="/paper" className="text-[var(--info-fg)] underline">
                  Paper Runs
                </Link>
                . The unified per-bot run feed lands in a Phase 2.5 follow-up alongside the
                full audit ledger.
              </p>
              <Separator className="my-3" />
              <p className="text-xs">
                Tenancy mode:{" "}
                <span className="font-mono uppercase">
                  {mode}
                </span>{" "}
                — actions taken from this page route through{" "}
                <code className="rounded bg-[var(--bg-app)] px-1 font-mono">
                  BotRuntime
                </code>{" "}
                and emit on{" "}
                <code className="rounded bg-[var(--bg-app)] px-1 font-mono">bot_versions</code> /{" "}
                <code className="rounded bg-[var(--bg-app)] px-1 font-mono">bot_deployments</code>.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        {data.kind === "research" ? (
          <TabsContent value="chat">
            <BotChatPanel botId={id} />
          </TabsContent>
        ) : null}
      </Tabs>

      {friction ? (
        <ConfirmFrictionDialog
          open={friction != null}
          onOpenChange={(open) => {
            if (!open) setFriction(null);
          }}
          title={`${FRICTION_LABEL[friction]} — ${data.name}`}
          consequence={
            friction === "halt"
              ? "Halts every running deployment, paper session, and backtest associated with this bot. In-flight orders may still settle."
              : friction === "deploy"
                ? mode === "live"
                  ? "Routes the active version through the live deployment dispatcher. Real capital may be at risk."
                  : "Routes the active version through the simulated deployment dispatcher."
                : friction === "paper"
                  ? "Starts a paper-broker session against the active spec. No real capital at risk."
                  : "Queues a backtest against the active spec. Read-only on capital; reads from the configured Iceberg dataset."
          }
          details={[
            { label: "Bot", value: data.name },
            { label: "Kind", value: data.kind },
            { label: "Version", value: data.current_version ?? "—" },
            { label: "Mode", value: mode.toUpperCase(), tone: mode === "live" ? "warn" : "neutral" },
          ]}
          confirmPhrase={friction === "halt" || (friction === "deploy" && mode === "live") ? friction.toUpperCase() : ""}
          confirmLabel={FRICTION_LABEL[friction]}
          confirmVariant={friction === "halt" ? "destructive" : friction === "deploy" ? "warn" : "default"}
          onConfirm={submit}
        />
      ) : null}
    </PageContainer>
  );
}
