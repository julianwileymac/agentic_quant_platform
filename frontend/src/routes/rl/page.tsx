import { Bot, FlaskConical, PlayCircle, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { RlApi, type RLAlgo, type RLApplication, type RLEnv, type RLRunSummary } from "@/lib/api/rl";
import { formatTime } from "@/lib/utils";
import { useTenancyStore } from "@/store/tenancy";

export function RlHomeRoute() {
  const navigate = useNavigate();
  const mode = useTenancyStore((s) => s.mode);
  const [confirm, setConfirm] = useState(false);
  const [name, setName] = useState("rl-quickstart");
  const [application, setApplication] = useState<string>("");
  const [algo, setAlgo] = useState<string>("");
  const [env, setEnv] = useState<string>("");
  const [hyperparams, setHyperparams] = useState<string>("{}");

  const algos = useApiQuery<RLAlgo[]>({
    queryKey: ["rl", "algos"],
    path: "/rl/algos",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const envs = useApiQuery<RLEnv[]>({
    queryKey: ["rl", "envs"],
    path: "/rl/envs",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const apps = useApiQuery<RLApplication[]>({
    queryKey: ["rl", "applications"],
    path: "/rl/applications",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const runs = useApiQuery<RLRunSummary[]>({
    queryKey: ["rl", "runs"],
    path: "/rl/runs",
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const selectedApp = useMemo(
    () => (apps.data ?? []).find((a) => a.key === application),
    [apps.data, application],
  );

  const submit = async () => {
    let parsed: Record<string, unknown> = {};
    if (hyperparams.trim()) {
      try {
        parsed = JSON.parse(hyperparams) as Record<string, unknown>;
      } catch {
        toast.error("Invalid hyperparams JSON");
        return;
      }
    }
    try {
      const res = await RlApi.startExperiment({
        application: application || "default",
        name,
        algo: algo || undefined,
        env: env || undefined,
        params: parsed,
      });
      toast.success(`RL experiment queued: ${res.task_id}`);
      runs.refetch();
      navigate(`/rl/runs/${res.task_id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`RL submit failed: ${msg}`);
      throw err;
    }
  };

  return (
    <PageContainer
      title="RL"
      subtitle="Spec-driven RL experiments. Every run goes through RLRuntime; trajectories land in the Iceberg rl.* tables."
      extra={
        <Button variant="ghost" size="sm" onClick={() => runs.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_320px]">
        <Card>
          <CardHeader>
            <CardTitle>Quick-start experiment</CardTitle>
            <Badge variant={mode === "live" ? "warn" : "secondary"} className="uppercase">
              {mode}
            </Badge>
          </CardHeader>
          <CardContent className="grid gap-3 lg:grid-cols-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="rl-name">Experiment name</Label>
              <Input id="rl-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="rl-app">Application</Label>
              <Input
                id="rl-app"
                list="rl-app-list"
                value={application}
                onChange={(e) => setApplication(e.target.value)}
                className="font-mono"
                placeholder="e.g. portfolio_management"
              />
              <datalist id="rl-app-list">
                {(apps.data ?? []).map((a) => (
                  <option key={a.key} value={a.key}>
                    {a.label}
                  </option>
                ))}
              </datalist>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="rl-algo">Algorithm</Label>
              <Input
                id="rl-algo"
                list="rl-algo-list"
                value={algo}
                onChange={(e) => setAlgo(e.target.value)}
                className="font-mono"
                placeholder={selectedApp?.default_algo ?? "ppo"}
              />
              <datalist id="rl-algo-list">
                {(algos.data ?? []).map((a) => (
                  <option key={a.key} value={a.key}>
                    {a.label}
                  </option>
                ))}
              </datalist>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="rl-env">Environment</Label>
              <Input
                id="rl-env"
                list="rl-env-list"
                value={env}
                onChange={(e) => setEnv(e.target.value)}
                className="font-mono"
                placeholder={selectedApp?.default_env ?? "stock-trading-v0"}
              />
              <datalist id="rl-env-list">
                {(envs.data ?? []).map((e) => (
                  <option key={e.key} value={e.key}>
                    {e.label}
                  </option>
                ))}
              </datalist>
            </div>
            <div className="flex flex-col gap-1 lg:col-span-2">
              <Label htmlFor="rl-hp">Hyperparams (JSON)</Label>
              <textarea
                id="rl-hp"
                rows={6}
                value={hyperparams}
                onChange={(e) => setHyperparams(e.target.value)}
                className="w-full resize-y rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs"
              />
            </div>
            <div className="flex items-center gap-2 lg:col-span-2">
              <Button onClick={() => setConfirm(true)} className="gap-2" disabled={!name.trim()}>
                <PlayCircle className="h-4 w-4" /> Start experiment
              </Button>
              <span className="text-xs text-[var(--text-secondary)]">
                Routes through{" "}
                <code className="rounded bg-[var(--bg-app)] px-1 font-mono">RLRuntime.train</code>;
                trajectories accrue in{" "}
                <code className="rounded bg-[var(--bg-app)] px-1 font-mono">rl.trajectories</code>.
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Catalog</CardTitle>
          </CardHeader>
          <CardContent className="text-xs">
            <p className="mb-1 font-medium uppercase tracking-wider text-[var(--text-secondary)]">
              Algos ({algos.data?.length ?? 0})
            </p>
            <ul className="mb-3 max-h-32 overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2">
              {(algos.data ?? []).map((a) => (
                <li key={a.key} className="flex items-center justify-between gap-2 py-0.5">
                  <span className="font-mono">{a.key}</span>
                  <span className="text-[var(--text-secondary)]">{a.framework}</span>
                </li>
              ))}
            </ul>
            <p className="mb-1 font-medium uppercase tracking-wider text-[var(--text-secondary)]">
              Envs ({envs.data?.length ?? 0})
            </p>
            <ul className="max-h-32 overflow-auto rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-2">
              {(envs.data ?? []).map((e) => (
                <li key={e.key} className="flex items-center justify-between gap-2 py-0.5">
                  <span className="font-mono">{e.key}</span>
                  <span className="text-[var(--text-secondary)]">{e.action_space}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-3">
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
          <Link to="/rl/zoo" className="text-xs text-[var(--info-fg)] underline">
            Browse RL Agent Zoo
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          <div className="h-[40vh]">
            <DataTable<RLRunSummary>
              rows={runs.data ?? []}
              rowKey={(r) => r.id}
              onRowClick={(r) => navigate(`/rl/runs/${r.id}`)}
              emptyState={
                <div className="flex flex-col items-center gap-2">
                  <Bot className="h-6 w-6" />
                  <span>No RL runs yet.</span>
                </div>
              }
              columns={[
                {
                  key: "name",
                  header: "Run",
                  render: (r) => (
                    <div className="flex flex-col">
                      <span className="font-medium">{r.experiment_name ?? r.id}</span>
                      <span className="font-mono text-[10px] text-[var(--text-muted)]">{r.id}</span>
                    </div>
                  ),
                },
                {
                  key: "algo",
                  header: "Algo",
                  width: 130,
                  render: (r) => <Badge variant="secondary">{r.algo ?? "—"}</Badge>,
                },
                {
                  key: "env",
                  header: "Env",
                  width: 130,
                  render: (r) => <span className="font-mono text-xs">{r.env ?? "—"}</span>,
                },
                {
                  key: "status",
                  header: "Status",
                  width: 110,
                  render: (r) => (
                    <Badge
                      variant={
                        r.status === "completed" ? "positive" : r.status === "failed" ? "negative" : r.status === "running" ? "default" : "secondary"
                      }
                    >
                      {r.status ?? "—"}
                    </Badge>
                  ),
                },
                {
                  key: "episodes",
                  header: "Episodes",
                  width: 100,
                  align: "right",
                  render: (r) => <Numeric value={r.episodes ?? null} kind="integer" digits={0} color="neutral" />,
                },
                {
                  key: "mean_return",
                  header: "Mean return",
                  width: 130,
                  align: "right",
                  render: (r) => <Numeric value={r.mean_return ?? null} kind="percent" digits={2} color="auto" signed />,
                },
                {
                  key: "started_at",
                  header: "Started",
                  width: 130,
                  align: "right",
                  render: (r) => (
                    <span className="text-[var(--text-secondary)]">{r.started_at ? formatTime(r.started_at) : "—"}</span>
                  ),
                },
              ]}
            />
          </div>
        </CardContent>
      </Card>

      {confirm ? (
        <ConfirmFrictionDialog
          open={confirm}
          onOpenChange={setConfirm}
          title={`Start RL experiment ${name}`}
          consequence="Queues a training job with RLRuntime. Trajectories, equity curves, and reward decompositions are persisted to the Iceberg rl.* tables, and an immutable rl_experiment_versions snapshot is created."
          details={[
            { label: "Application", value: application || "default" },
            { label: "Algo", value: algo || selectedApp?.default_algo || "ppo" },
            { label: "Env", value: env || selectedApp?.default_env || "stock-trading-v0" },
            { label: "Mode", value: mode.toUpperCase(), tone: mode === "live" ? "warn" : "neutral" },
          ]}
          confirmPhrase=""
          confirmLabel="Start training"
          confirmVariant="default"
          onConfirm={submit}
        >
          {!apps.isPending && !algos.isPending && (algos.data?.length === 0 || envs.data?.length === 0) ? (
            <div className="flex items-center gap-2 rounded-md border border-[var(--warn-fg)] bg-[var(--warn-bg)] p-2 text-xs text-[var(--warn-fg)]">
              <FlaskConical className="h-4 w-4" /> Backend has no algos / envs registered. The
              experiment will fail unless RL components are seeded.
            </div>
          ) : null}
        </ConfirmFrictionDialog>
      ) : null}
    </PageContainer>
  );
}
