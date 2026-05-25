import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { adminApi, type JsonObject } from "@/lib/api";

export function KubernetesIndex() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["kubernetes", "status"],
    queryFn: adminApi.kubernetesStatus,
    refetchInterval: 30000,
  });
  const namespaces = useQuery({
    queryKey: ["kubernetes", "namespaces"],
    queryFn: adminApi.listKubernetesNamespaces,
    refetchInterval: 30000,
  });
  const [namespace, setNamespace] = useState("");
  const [selectedPod, setSelectedPod] = useState<JsonObject | null>(null);
  const [command, setCommand] = useState("python --version");
  const [confirmExec, setConfirmExec] = useState(false);

  const pods = useQuery({
    queryKey: ["kubernetes", "pods", namespace],
    queryFn: () => adminApi.listPods(namespace),
    enabled: !!namespace,
    refetchInterval: 10000,
  });

  const exec = useMutation({
    mutationFn: async () => {
      if (!selectedPod) throw new Error("Select a pod first.");
      const name = podName(selectedPod);
      const argv = command.split(" ").map((part) => part.trim()).filter(Boolean);
      return adminApi.execInPod(namespace, name, { command: argv, timeout_seconds: 60 });
    },
    onSuccess: () => {
      setConfirmExec(false);
      void qc.invalidateQueries({ queryKey: ["kubernetes", "pods", namespace] });
    },
  });

  const namespaceOptions = useMemo(
    () => namespaces.data?.namespaces.map((item) => String(item.namespace ?? "")) ?? [],
    [namespaces.data?.namespaces],
  );

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Kubernetes</h1>
        <p className="text-sm text-muted-foreground">
          Cluster status and pod diagnostics brokered through the monolith
          KubernetesAdapter. Use Services for deployment-level start/stop/scale.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="rounded-lg border bg-card p-4">
          <h2 className="mb-2 text-lg font-medium">Adapter status</h2>
          {status.isLoading ? <p className="text-sm">Loading...</p> : null}
          {status.error ? <p className="text-sm text-red-600">{status.error.message}</p> : null}
          <pre className="max-h-56 overflow-auto rounded bg-slate-50 p-2 text-xs">
            {JSON.stringify(status.data ?? null, null, 2)}
          </pre>
        </div>

        <div className="rounded-lg border bg-card p-4 xl:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-medium">Namespaces</h2>
            <button
              type="button"
              className="rounded border px-2 py-1 text-xs"
              onClick={() => void namespaces.refetch()}
            >
              Refresh
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {namespaceOptions.map((item) => (
              <button
                key={item}
                type="button"
                className={`rounded-full border px-3 py-1 text-xs ${
                  namespace === item ? "bg-slate-900 text-white" : "bg-white"
                }`}
                onClick={() => {
                  setNamespace(item);
                  setSelectedPod(null);
                }}
              >
                {item}
              </button>
            ))}
            {namespaceOptions.length === 0 ? (
              <p className="text-sm text-slate-500">No namespaces inferred from deployments.</p>
            ) : null}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded-lg border bg-card p-4">
          <h2 className="mb-3 text-lg font-medium">Pods {namespace ? `in ${namespace}` : ""}</h2>
          {!namespace ? <p className="text-sm text-slate-500">Select a namespace.</p> : null}
          {pods.error ? <p className="text-sm text-red-600">{pods.error.message}</p> : null}
          <ul className="space-y-2 text-sm">
            {(pods.data?.pods ?? []).map((pod) => {
              const name = podName(pod);
              const phase = podPhase(pod);
              return (
                <li key={name}>
                  <button
                    type="button"
                    className="w-full rounded border p-2 text-left hover:bg-slate-50"
                    onClick={() => setSelectedPod(pod)}
                  >
                    <div className="flex justify-between">
                      <span className="font-mono text-xs">{name}</span>
                      <span>{phase}</span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="rounded-lg border bg-card p-4">
          <h2 className="mb-3 text-lg font-medium">Selected pod</h2>
          {selectedPod ? (
            <div className="space-y-3">
              <pre className="max-h-56 overflow-auto rounded bg-slate-50 p-2 text-xs">
                {JSON.stringify(selectedPod, null, 2)}
              </pre>
              <label className="block space-y-1">
                <span className="text-xs font-medium text-slate-500">Exec command</span>
                <input
                  className="w-full rounded-md border px-3 py-2 text-sm"
                  value={command}
                  onChange={(event) => setCommand(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white"
                onClick={() => setConfirmExec(true)}
              >
                Exec with confirmation
              </button>
              {exec.data ? (
                <pre className="max-h-56 overflow-auto rounded bg-slate-50 p-2 text-xs">
                  {JSON.stringify(exec.data, null, 2)}
                </pre>
              ) : null}
              {exec.error ? <p className="text-sm text-red-600">{exec.error.message}</p> : null}
            </div>
          ) : (
            <p className="text-sm text-slate-500">Select a pod to inspect.</p>
          )}
        </div>
      </div>

      <ConfirmFrictionDialog
        open={confirmExec}
        title="Exec into pod?"
        description={
          <>
            This executes a command inside the selected pod and writes an admin
            audit row before dispatching.
          </>
        }
        confirmPhrase="exec"
        destructive={false}
        busy={exec.isPending}
        onCancel={() => setConfirmExec(false)}
        onConfirm={() => exec.mutate()}
      />
    </section>
  );
}

function objectField(input: JsonObject, key: string): JsonObject | null {
  const value = input[key];
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function podName(pod: JsonObject): string {
  return String(pod.name ?? objectField(pod, "metadata")?.name ?? "");
}

function podPhase(pod: JsonObject): string {
  return String(pod.phase ?? objectField(pod, "status")?.phase ?? "unknown");
}
