import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { toast } from "@/components/ui/toast";
import {
  type DeploymentStatus,
  listDeployments,
  restartDeployment,
  scaleDeployment,
  startDeployment,
  stopDeployment,
} from "@/lib/api/workloads";

/**
 * Workload Studio — single Vite surface for the Management Engine
 * (`/manage/*` proxy or embedded). Operators see every workload from
 * every provider (docker_compose / kubernetes / aws / azure / gcp /
 * cloudflare) and can start / stop / scale / restart with the existing
 * ConfirmFrictionDialog gating.
 */
export function ManageStudioRoute(): React.ReactElement {
  const qc = useQueryClient();
  const { data: deployments = [], isLoading } = useQuery({
    queryKey: ["manage", "deployments"],
    queryFn: () => listDeployments(),
    refetchInterval: 5_000,
  });

  const startMut = useMutation({
    mutationFn: ({ id, spec }: { id: string; spec: Record<string, unknown> }) =>
      startDeployment(id, spec),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["manage", "deployments"] }),
  });
  const stopMut = useMutation({
    mutationFn: ({ id, ns }: { id: string; ns?: string }) =>
      stopDeployment(id, ns),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["manage", "deployments"] }),
  });
  const restartMut = useMutation({
    mutationFn: ({ id, ns }: { id: string; ns?: string }) =>
      restartDeployment(id, ns),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["manage", "deployments"] }),
  });
  const scaleMut = useMutation({
    mutationFn: ({
      id,
      replicas,
      ns,
    }: { id: string; replicas: number; ns?: string }) =>
      scaleDeployment(id, replicas, ns),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["manage", "deployments"] }),
  });

  const [confirm, setConfirm] = useState<
    | { kind: "stop" | "restart"; id: string; ns?: string }
    | null
  >(null);

  return (
    <div className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Workload Studio</h1>
          <p className="text-muted-foreground text-sm">
            Direct control over every workload via the AQP Management Engine.
            All actions are audited in <code>workload_runs</code>.
          </p>
        </div>
        <Badge variant="outline">{deployments.length} deployments</Badge>
      </header>

      <div className="grid gap-4">
        {isLoading ? (
          <p className="text-muted-foreground">Loading deployments…</p>
        ) : (
          deployments.map((d) => (
            <DeploymentRow
              key={`${d.provider}-${d.namespace ?? "_"}-${d.service_id}`}
              row={d}
              onStop={() =>
                setConfirm({
                  kind: "stop",
                  id: d.service_id,
                  ns: d.namespace ?? undefined,
                })
              }
              onRestart={() =>
                setConfirm({
                  kind: "restart",
                  id: d.service_id,
                  ns: d.namespace ?? undefined,
                })
              }
              onStart={() => {
                startMut.mutate(
                  {
                    id: d.service_id,
                    spec: { image: d.image ?? "", replicas: 1, namespace: d.namespace },
                  },
                  {
                    onSuccess: () =>
                      toast.success(`started ${d.service_id}`),
                    onError: (err) =>
                      toast.error(`failed to start ${d.service_id}`, {
                        description: String(err),
                      }),
                  },
                );
              }}
              onScale={(replicas) =>
                scaleMut.mutate(
                  { id: d.service_id, replicas, ns: d.namespace ?? undefined },
                  {
                    onSuccess: () =>
                      toast.success(`scaled ${d.service_id} -> ${replicas}`),
                    onError: (err) =>
                      toast.error(`scale failed for ${d.service_id}`, {
                        description: String(err),
                      }),
                  },
                )
              }
            />
          ))
        )}
      </div>

      <ConfirmFrictionDialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm?.kind === "stop"
            ? `Stop ${confirm?.id}`
            : `Restart ${confirm?.id}`
        }
        consequence={
          confirm?.kind === "stop"
            ? "Scales the deployment to zero. In-flight traffic may drop until restart."
            : "Triggers a rolling restart; pods reload secrets + config on next reconcile."
        }
        confirmPhrase={confirm?.kind === "stop" ? "STOP" : "RESTART"}
        confirmLabel={confirm?.kind === "stop" ? "Stop deployment" : "Restart deployment"}
        confirmVariant={confirm?.kind === "stop" ? "destructive" : "default"}
        onConfirm={async () => {
          if (!confirm) return;
          if (confirm.kind === "stop") {
            stopMut.mutate(
              { id: confirm.id, ns: confirm.ns },
              {
                onSuccess: () => toast.success(`stopped ${confirm.id}`),
                onError: (err) =>
                  toast.error(`stop failed`, { description: String(err) }),
              },
            );
          } else {
            restartMut.mutate(
              { id: confirm.id, ns: confirm.ns },
              {
                onSuccess: () => toast.success(`restarted ${confirm.id}`),
                onError: (err) =>
                  toast.error(`restart failed`, { description: String(err) }),
              },
            );
          }
          setConfirm(null);
        }}
      />
    </div>
  );
}

function DeploymentRow({
  row,
  onStop,
  onRestart,
  onStart,
  onScale,
}: {
  row: DeploymentStatus;
  onStop: () => void;
  onRestart: () => void;
  onStart: () => void;
  onScale: (replicas: number) => void;
}) {
  const isRunning = row.replicas_ready > 0;
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-medium font-mono">{row.service_id}</h3>
            <Badge variant="outline">{row.provider}</Badge>
            <Badge
              variant={isRunning ? "default" : "destructive"}
              className="capitalize"
            >
              {row.phase}
            </Badge>
            {row.namespace && (
              <Badge variant="secondary">ns: {row.namespace}</Badge>
            )}
          </div>
          {row.image && (
            <p className="mt-1 text-muted-foreground text-xs font-mono">
              {row.image}
            </p>
          )}
          <p className="mt-1 text-muted-foreground text-xs tabular-nums">
            {row.replicas_ready} / {row.replicas_desired} replicas ready
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isRunning ? (
            <Button size="sm" variant="outline" onClick={onStop}>
              Stop
            </Button>
          ) : (
            <Button size="sm" variant="default" onClick={onStart}>
              Start
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onRestart}>
            Restart
          </Button>
          <input
            type="number"
            min={0}
            max={50}
            defaultValue={row.replicas_desired}
            className="w-16 rounded border border-input bg-transparent px-2 py-1 text-sm tabular-nums"
            aria-label={`Replica count for ${row.service_id}`}
            onBlur={(e) => {
              const n = Number(e.currentTarget.value);
              if (!Number.isNaN(n) && n !== row.replicas_desired) {
                onScale(n);
              }
            }}
          />
        </div>
      </div>
    </Card>
  );
}
