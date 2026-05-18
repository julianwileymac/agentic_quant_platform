import { useMemo, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import {
  terraformApi,
  type TerraformWorkspace,
  type TerraformRun,
} from "@/lib/api/terraform";
import { useEffect } from "react";

import { LocalStackCard } from "./LocalStackCard";

/**
 * /infra/terraform — Terraform workspace IDE.
 *
 * - Lists every TerraformWorkspace.
 * - Per-row Plan / Apply / Destroy buttons, all friction-gated.
 * - Apply requires a successful plan run id (the route validates).
 * - Destroy requires the user to type the workspace slug.
 */
export function InfraTerraformRoute() {
  const [workspaces, setWorkspaces] = useState<TerraformWorkspace[]>([]);
  const [runs, setRuns] = useState<TerraformRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingDestroy, setPendingDestroy] = useState<TerraformWorkspace | null>(null);

  const load = async () => {
    try {
      const [ws, rs] = await Promise.all([
        terraformApi.listWorkspaces(),
        terraformApi.listRuns({ limit: 50 }),
      ]);
      setWorkspaces(ws.items);
      setRuns(rs.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15_000);
    return () => clearInterval(t);
  }, []);

  const lastRunByWs = useMemo(() => {
    const map = new Map<string, TerraformRun>();
    for (const r of runs) {
      const existing = map.get(r.terraform_workspace_id);
      if (!existing || (r.started_at ?? "") > (existing.started_at ?? "")) {
        map.set(r.terraform_workspace_id, r);
      }
    }
    return map;
  }, [runs]);

  const plan = async (ws: TerraformWorkspace) => {
    try {
      await terraformApi.plan(ws.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const apply = async (ws: TerraformWorkspace) => {
    const lastPlan = runs.find(
      (r) => r.terraform_workspace_id === ws.id && r.run_kind === "plan" && r.status === "completed",
    );
    if (!lastPlan) {
      setError(`No completed plan run for workspace ${ws.slug!}; run plan first.`);
      return;
    }
    try {
      await terraformApi.apply(ws.id, lastPlan.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const destroyConfirmed = async () => {
    if (!pendingDestroy) return;
    try {
      await terraformApi.destroy(pendingDestroy.id, pendingDestroy.slug);
      setPendingDestroy(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <PageContainer
      title="Terraform IaC"
      subtitle="Plan / apply / destroy AQP stacks across local + cloud + rpi_cluster"
    >
      <LocalStackCard />
      {error && (
        <div className="mb-3 rounded border border-[var(--neg-border,#dc2626)] bg-[var(--bg-card)] p-2 text-xs text-[var(--neg-fg)]">
          {error}
        </div>
      )}
      <div className="overflow-x-auto rounded border border-[var(--border-default)]">
        <table className="w-full text-xs">
          <thead className="bg-[var(--bg-card)]">
            <tr>
              <th className="px-2 py-1 text-left">Slug</th>
              <th className="px-2 py-1 text-left">Env</th>
              <th className="px-2 py-1 text-left">Backend</th>
              <th className="px-2 py-1 text-left">Last run</th>
              <th className="px-2 py-1 text-left">Status</th>
              <th className="px-2 py-1 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {workspaces.map((ws) => {
              const last = lastRunByWs.get(ws.id);
              return (
                <tr
                  key={ws.id}
                  className="border-t border-[var(--border-default)] hover:bg-[var(--bg-hover)]"
                >
                  <td className="px-2 py-1 font-mono">{ws.slug}</td>
                  <td className="px-2 py-1">{ws.environment}</td>
                  <td className="px-2 py-1">{ws.state_backend}</td>
                  <td className="px-2 py-1 font-mono">{last?.run_kind ?? "—"}</td>
                  <td className="px-2 py-1">
                    <StatusBadge status={last?.status} />
                  </td>
                  <td className="space-x-1 px-2 py-1 text-right">
                    <Button size="sm" variant="outline" onClick={() => plan(ws)}>
                      Plan
                    </Button>
                    <Button size="sm" variant="default" onClick={() => apply(ws)}>
                      Apply
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => setPendingDestroy(ws)}
                    >
                      Destroy
                    </Button>
                  </td>
                </tr>
              );
            })}
            {workspaces.length === 0 && (
              <tr>
                <td className="px-2 py-1 text-[var(--text-secondary)]" colSpan={6}>
                  No workspaces yet. Create one via the Terraform stack composer
                  or the API:{" "}
                  <code className="font-mono">POST /terraform/workspaces</code>.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pendingDestroy && (
        <ConfirmFrictionDialog
          open={true}
          onOpenChange={(open) => !open && setPendingDestroy(null)}
          title={`Destroy workspace ${pendingDestroy.slug}`}
          consequence="This runs ``terraform destroy`` against the workspace and tears down EVERY resource it manages. Cannot be reversed automatically."
          confirmPhrase={pendingDestroy.slug}
          confirmLabel="Destroy stack"
          confirmVariant="destructive"
          onConfirm={destroyConfirmed}
        />
      )}
    </PageContainer>
  );
}

function StatusBadge({ status }: { status: string | undefined }) {
  if (!status) return <span className="text-[var(--text-secondary)]">—</span>;
  const color =
    status === "completed"
      ? "var(--pos-fg)"
      : status === "errored" || status === "cancelled" || status === "policy_failed"
        ? "var(--neg-fg)"
        : "var(--warn-fg)";
  return (
    <span className="font-mono uppercase" style={{ color }}>
      {status}
    </span>
  );
}

export default InfraTerraformRoute;
