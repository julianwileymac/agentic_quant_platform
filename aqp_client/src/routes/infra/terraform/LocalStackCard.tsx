import { Loader2, Power, Hammer, RotateCcw, Rocket } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { terraformApi, type LocalStackEndpoints } from "@/lib/api/terraform";
import { useChatStream } from "@/lib/ws";

const STACK_NAME = "aqp-local";

interface ProgressLine {
  stage: string;
  message: string;
  ts: string;
}

/**
 * Local Stack card for /infra/terraform.
 *
 * Surfaces the canonical aqp-local Terraform stack with one-click
 * Up / Build / Down / Refresh actions, a live ProgressTimeline keyed
 * off the returned task_id, a pod-status rollup, and copy-to-clipboard
 * endpoint chips. Every mutation routes through ``aqp.tasks.terraform_tasks
 * .run_local_stack`` so each apply lands a row in ``terraform_runs``
 * and is halt-able from the global KillSwitch (rule 42).
 */
export function LocalStackCard() {
  const [endpoints, setEndpoints] = useState<LocalStackEndpoints | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDestroy, setPendingDestroy] = useState(false);
  const [progress, setProgress] = useState<ProgressLine[]>([]);

  const stream = useChatStream(taskId, "terraform");

  useEffect(() => {
    if (!taskId) {
      setProgress([]);
      return;
    }
    const lines: ProgressLine[] = stream.events.map((event) => ({
      stage: String(event.stage ?? "running"),
      message: String(event.message ?? event.delta ?? ""),
      ts: String(event.timestamp ?? ""),
    }));
    setProgress(lines);
  }, [stream.events, taskId]);

  const refreshEndpoints = async () => {
    try {
      const resp = await terraformApi.localStackEndpoints(STACK_NAME);
      setEndpoints(resp);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    }
  };

  useEffect(() => {
    refreshEndpoints();
    const t = setInterval(refreshEndpoints, 30_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (stream.done) {
      setBusyAction(null);
      void refreshEndpoints();
    }
  }, [stream.done]);

  const dispatch = async (
    action: "up" | "build" | "down" | "refresh",
    fn: () => Promise<{ task_id: string }>,
  ) => {
    setError(null);
    setBusyAction(action);
    setProgress([]);
    try {
      const res = await fn();
      setTaskId(res.task_id);
    } catch (e) {
      setBusyAction(null);
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    }
  };

  const onUp = () =>
    dispatch("up", () => terraformApi.localStackUp(STACK_NAME));
  const onBuild = () =>
    dispatch("build", () => terraformApi.localStackBuild(STACK_NAME));
  const onRefresh = () =>
    dispatch("refresh", () => terraformApi.localStackRefresh(STACK_NAME));
  const confirmDown = async () => {
    setPendingDestroy(false);
    await dispatch("down", () => terraformApi.localStackDown(STACK_NAME));
  };

  const podCounts = endpoints?.pods ?? {};
  const podBadges = useMemo(
    () => [
      { key: "running", label: "Running", value: podCounts.running ?? 0, tone: "positive" },
      { key: "pending", label: "Pending", value: podCounts.pending ?? 0, tone: "warn" },
      { key: "failed", label: "Failed", value: podCounts.failed ?? 0, tone: "negative" },
      { key: "total", label: "Total", value: podCounts.total ?? 0, tone: "muted" },
    ],
    [podCounts],
  );

  const endpointEntries: Array<[string, string | null | undefined]> = endpoints
    ? [
        ["Frontend", endpoints.frontend_url],
        ["API", endpoints.api_url],
        ["MLflow", endpoints.mlflow_url],
        ["Jaeger", endpoints.jaeger_url],
        ["Cluster", endpoints.cluster_name],
        ["Namespace", endpoints.namespace],
        ["Registry", endpoints.registry],
      ]
    : [];

  return (
    <section className="mb-4 rounded border border-[var(--border-default)] bg-[var(--bg-card)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Local Stack ({STACK_NAME})</h3>
          <p className="text-[11px] text-[var(--text-secondary)]">
            k3d cluster + image build/push + Kubernetes workloads. Replaces docker-compose; every action lands a terraform_runs row and is halt-able from the global KillSwitch.
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          <Button size="sm" variant="default" disabled={!!busyAction} onClick={onUp}>
            {busyAction === "up" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Rocket className="h-3 w-3" />}
            <span className="ml-1">Up</span>
          </Button>
          <Button size="sm" variant="outline" disabled={!!busyAction} onClick={onBuild}>
            {busyAction === "build" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Hammer className="h-3 w-3" />}
            <span className="ml-1">Build</span>
          </Button>
          <Button size="sm" variant="outline" disabled={!!busyAction} onClick={onRefresh}>
            {busyAction === "refresh" ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />}
            <span className="ml-1">Refresh</span>
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={!!busyAction}
            onClick={() => setPendingDestroy(true)}
          >
            <Power className="h-3 w-3" />
            <span className="ml-1">Down</span>
          </Button>
        </div>
      </div>

      {error && (
        <div className="mt-2 rounded border border-[var(--neg-border,#dc2626)] bg-[var(--bg-app)] p-2 text-xs text-[var(--neg-fg,#dc2626)]">
          {error}
        </div>
      )}

      <div className="mt-3 grid gap-2 md:grid-cols-[180px_1fr]">
        <div className="rounded border border-[var(--border-default)] bg-[var(--bg-app)] p-2 text-xs">
          <div className="font-semibold uppercase text-[var(--text-secondary)] text-[10px] mb-1">Pods</div>
          <ul className="grid gap-0.5">
            {podBadges.map((badge) => (
              <li key={badge.key} className="flex items-center justify-between">
                <span className="text-[var(--text-secondary)]">{badge.label}</span>
                <span className="font-mono">{badge.value}</span>
              </li>
            ))}
          </ul>
          {endpoints?.table_present === false && (
            <div className="mt-2 text-[10px] italic text-[var(--text-secondary)]">
              terraform output unavailable; run aqp deploy up first.
            </div>
          )}
        </div>

        <div className="rounded border border-[var(--border-default)] bg-[var(--bg-app)] p-2 text-xs">
          <div className="font-semibold uppercase text-[var(--text-secondary)] text-[10px] mb-1">Endpoints</div>
          <div className="grid gap-1">
            {endpointEntries.length === 0 && (
              <div className="text-[var(--text-secondary)] italic">
                No endpoints yet. Run Up to create the cluster.
              </div>
            )}
            {endpointEntries.map(([label, value]) =>
              value ? (
                <button
                  key={label}
                  className="flex items-center justify-between rounded border border-[var(--border-default)] bg-[var(--bg-card)] px-2 py-1 text-left font-mono hover:bg-[var(--bg-hover)]"
                  onClick={() => navigator.clipboard?.writeText(String(value))}
                  title="Copy"
                >
                  <span className="text-[var(--text-secondary)] uppercase text-[10px]">{label}</span>
                  <span className="truncate ml-2">{value}</span>
                </button>
              ) : null,
            )}
          </div>
        </div>
      </div>

      {(taskId || progress.length > 0) && (
        <div className="mt-3 rounded border border-[var(--border-default)] bg-[var(--bg-app)] p-2 text-xs">
          <div className="flex items-center justify-between">
            <div className="font-semibold uppercase text-[var(--text-secondary)] text-[10px]">
              Progress {busyAction ? `(${busyAction})` : ""}
            </div>
            {taskId && (
              <code className="font-mono text-[10px] text-[var(--text-secondary)]">
                task: {taskId.slice(0, 8)}…
              </code>
            )}
          </div>
          <ul className="mt-1 max-h-48 overflow-y-auto font-mono text-[11px]">
            {progress.length === 0 && (
              <li className="text-[var(--text-secondary)] italic">Waiting for the first frame…</li>
            )}
            {progress.map((line, idx) => (
              <li key={idx} className="flex gap-2">
                <span className="text-[var(--text-secondary)]">[{line.stage}]</span>
                <span>{line.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {pendingDestroy && (
        <ConfirmFrictionDialog
          open={pendingDestroy}
          onOpenChange={(open) => !open && setPendingDestroy(false)}
          title="Tear down the local AQP stack"
          consequence="This runs 'terraform destroy' on the entire local k3d stack. Every Kubernetes resource AND the cluster itself will be deleted. Image registry contents are wiped. Iceberg / Postgres data persisted on the host filesystem survives, but in-cluster volumes are lost. Cannot be reversed."
          confirmPhrase="DESTROY"
          confirmLabel="Tear down local stack"
          confirmVariant="destructive"
          onConfirm={confirmDown}
        />
      )}
    </section>
  );
}
