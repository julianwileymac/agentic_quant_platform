import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { adminApi, type JsonObject } from "@/lib/api";

type TerraformAction = "plan" | "validate" | "apply" | "destroy";

export function TerraformIndex() {
  const qc = useQueryClient();
  const providers = useQuery({
    queryKey: ["terraform", "providers"],
    queryFn: adminApi.listTerraformProviders,
  });
  const stacks = useQuery({
    queryKey: ["terraform", "stacks"],
    queryFn: adminApi.listTerraformStacks,
  });
  const workspaces = useQuery({
    queryKey: ["terraform", "workspaces"],
    queryFn: adminApi.listTerraformWorkspaces,
    refetchInterval: 30000,
  });
  const runs = useQuery({
    queryKey: ["terraform", "runs"],
    queryFn: () => adminApi.listTerraformRuns(),
    refetchInterval: 10000,
  });
  const halt = useQuery({
    queryKey: ["terraform", "halt"],
    queryFn: adminApi.terraformHaltStatus,
    refetchInterval: 15000,
  });
  const [workspaceId, setWorkspaceId] = useState("");
  const [specJson, setSpecJson] = useState("{\n  \"stack_name\": \"\",\n  \"workspace_id\": \"\"\n}");
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<TerraformAction | null>(null);

  const run = useMutation({
    mutationFn: async (action: TerraformAction) => {
      const spec = JSON.parse(specJson) as JsonObject;
      return adminApi.runTerraformWorkspace(workspaceId, action, { spec });
    },
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["terraform", "runs"] });
    },
    onError: (err: Error) => setError(err.message),
    onSettled: () => setPendingAction(null),
  });

  const selectedWorkspace = useMemo(() => {
    return (workspaces.data?.items ?? []).find((item) => item.id === workspaceId);
  }, [workspaces.data?.items, workspaceId]);

  function execute(action: TerraformAction) {
    if (!workspaceId.trim()) {
      setError("Select a workspace first.");
      return;
    }
    try {
      JSON.parse(specJson);
    } catch {
      setError("Terraform spec JSON must be valid.");
      return;
    }
    if (action === "apply" || action === "destroy") {
      setPendingAction(action);
    } else {
      run.mutate(action);
    }
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Terraform</h1>
        <p className="text-sm text-muted-foreground">
          Browse Terraform metadata from the monolith and execute
          plan/validate/apply/destroy through the control-plane
          TerraformRuntime.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-4">
        <StatusCard title="Providers" value={providers.data?.items.length ?? 0} />
        <StatusCard title="Stacks" value={stacks.data?.items.length ?? 0} />
        <StatusCard title="Workspaces" value={workspaces.data?.items.length ?? 0} />
        <StatusCard
          title="Terraform halt"
          value={halt.data?.data && typeof halt.data.data === "object" && "active" in halt.data.data
            ? String((halt.data.data as { active?: boolean }).active)
            : "unknown"}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="space-y-4 rounded-lg border bg-card p-4 xl:col-span-2">
          <h2 className="text-lg font-medium">Workspace action</h2>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-slate-500">Workspace</span>
            <select
              className="w-full rounded-md border px-3 py-2 text-sm"
              value={workspaceId}
              onChange={(event) => setWorkspaceId(event.target.value)}
            >
              <option value="">Select workspace...</option>
              {(workspaces.data?.items ?? []).map((workspace) => (
                <option key={String(workspace.id)} value={String(workspace.id)}>
                  {String(workspace.slug ?? workspace.name ?? workspace.id)}
                </option>
              ))}
            </select>
          </label>
          {selectedWorkspace ? (
            <pre className="max-h-32 overflow-auto rounded bg-slate-50 p-2 text-xs">
              {JSON.stringify(selectedWorkspace, null, 2)}
            </pre>
          ) : null}
          <label className="block space-y-1">
            <span className="text-xs font-medium text-slate-500">
              TerraformStackSpec JSON sent to the control plane
            </span>
            <textarea
              className="min-h-60 w-full rounded-md border px-3 py-2 font-mono text-xs"
              value={specJson}
              onChange={(event) => setSpecJson(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            {(["validate", "plan", "apply", "destroy"] as const).map((action) => (
              <button
                key={action}
                type="button"
                disabled={run.isPending}
                className={`rounded-md px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50 ${
                  action === "destroy" ? "bg-red-600" : "bg-slate-900"
                }`}
                onClick={() => execute(action)}
              >
                {run.isPending && pendingAction === action ? "Running..." : action}
              </button>
            ))}
          </div>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          {run.data ? (
            <pre className="max-h-60 overflow-auto rounded bg-slate-50 p-3 text-xs">
              {JSON.stringify(run.data, null, 2)}
            </pre>
          ) : null}
        </div>

        <div className="rounded-lg border bg-card p-4">
          <h2 className="mb-3 text-lg font-medium">Recent runs</h2>
          <ul className="space-y-2 text-sm">
            {(runs.data?.items ?? []).slice(0, 20).map((item) => (
              <li key={String(item.id)} className="rounded border p-2">
                <div className="flex justify-between">
                  <span className="font-mono text-xs">{String(item.run_kind ?? "run")}</span>
                  <span>{String(item.status ?? "unknown")}</span>
                </div>
                <div className="mt-1 truncate font-mono text-xs text-slate-500">
                  {String(item.id ?? "")}
                </div>
              </li>
            ))}
            {runs.data?.items.length === 0 ? (
              <li className="text-sm text-slate-500">No Terraform runs yet.</li>
            ) : null}
          </ul>
        </div>
      </div>

      <ConfirmFrictionDialog
        open={pendingAction === "apply" || pendingAction === "destroy"}
        title={`${pendingAction ?? "terraform"} workspace?`}
        description={
          <>
            This dispatches <code>{pendingAction}</code> through the control
            plane. Upstream authorization, step-up, and four-eyes checks still apply.
          </>
        }
        confirmPhrase={pendingAction ?? "confirm"}
        destructive={pendingAction === "destroy"}
        busy={run.isPending}
        onCancel={() => setPendingAction(null)}
        onConfirm={() => pendingAction && run.mutate(pendingAction)}
      />
    </section>
  );
}

function StatusCard({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}
