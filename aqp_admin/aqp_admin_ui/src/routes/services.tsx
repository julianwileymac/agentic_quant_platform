import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { adminApi } from "@/lib/api";

type PendingAction =
  | { kind: "restart"; serviceId: string; namespace?: string | null }
  | { kind: "stop"; serviceId: string; namespace?: string | null }
  | null;

export function ServicesRoute() {
  const qc = useQueryClient();
  const services = useQuery({
    queryKey: ["services"],
    queryFn: () => adminApi.listServices(),
  });
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [scaleReplicas, setScaleReplicas] = useState<Record<string, number>>({});
  const serviceAction = useMutation({
    mutationFn: async (action: Exclude<PendingAction, null>) => {
      if (action.kind === "restart") {
        return adminApi.restartService(action.serviceId, action.namespace);
      }
      return adminApi.stopService(action.serviceId, action.namespace);
    },
    onSuccess: () => {
      setPendingAction(null);
      void qc.invalidateQueries({ queryKey: ["services"] });
    },
  });
  const scale = useMutation({
    mutationFn: async (input: { serviceId: string; namespace?: string | null; replicas: number }) =>
      adminApi.scaleService(input.serviceId, {
        namespace: input.namespace,
        replicas: input.replicas,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["services"] }),
  });

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Managed services</h1>
        <p className="text-sm text-muted-foreground">
          Deployment-level control for AQP managed services, brokered through
          the control-plane WorkloadRuntime.
        </p>
      </header>
      <div className="overflow-hidden rounded-lg border bg-card">
        {services.isLoading && <p className="p-4 text-sm">Loading services...</p>}
        {services.error ? <p className="p-4 text-sm text-red-600">{services.error.message}</p> : null}
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Service</th>
              <th className="px-3 py-2">Namespace</th>
              <th className="px-3 py-2">Phase</th>
              <th className="px-3 py-2">Image</th>
              <th className="px-3 py-2">Replicas</th>
              <th className="px-3 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(services.data?.services ?? []).map((service) => {
              const replicas = scaleReplicas[service.id] ?? service.replicas_desired ?? 0;
              return (
                <tr key={service.id} className="border-t">
                  <td className="px-3 py-2 font-mono text-xs">{service.id}</td>
                  <td className="px-3 py-2">{service.namespace ?? "n/a"}</td>
                  <td className="px-3 py-2">{service.phase ?? service.state}</td>
                  <td className="max-w-xs truncate px-3 py-2 text-xs">{service.image ?? "n/a"}</td>
                  <td className="px-3 py-2">
                    {service.replicas_ready}/{service.replicas_desired}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        className="w-16 rounded border px-2 py-1 text-xs"
                        type="number"
                        min={0}
                        value={replicas}
                        onChange={(event) =>
                          setScaleReplicas((prev) => ({
                            ...prev,
                            [service.id]: Number(event.target.value),
                          }))
                        }
                      />
                      <button
                        type="button"
                        className="rounded border px-2 py-1 text-xs"
                        onClick={() =>
                          scale.mutate({
                            serviceId: service.id,
                            namespace: service.namespace,
                            replicas,
                          })
                        }
                      >
                        Scale
                      </button>
                      <button
                        type="button"
                        className="rounded border px-2 py-1 text-xs"
                        onClick={() =>
                          setPendingAction({
                            kind: "restart",
                            serviceId: service.id,
                            namespace: service.namespace,
                          })
                        }
                      >
                        Restart
                      </button>
                      <button
                        type="button"
                        className="rounded border border-red-300 px-2 py-1 text-xs text-red-700"
                        onClick={() =>
                          setPendingAction({
                            kind: "stop",
                            serviceId: service.id,
                            namespace: service.namespace,
                          })
                        }
                      >
                        Stop
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {services.data?.services.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                  No managed services configured yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {serviceAction.error ? (
        <p className="text-sm text-red-600">{serviceAction.error.message}</p>
      ) : null}
      {scale.error ? <p className="text-sm text-red-600">{scale.error.message}</p> : null}

      <ConfirmFrictionDialog
        open={pendingAction !== null}
        title={`${pendingAction?.kind ?? "service"} managed service?`}
        description={
          <>
            This sends a <code>{pendingAction?.kind}</code> request through the
            control plane and records an admin audit row before dispatch.
          </>
        }
        confirmPhrase={pendingAction?.kind ?? "confirm"}
        destructive={pendingAction?.kind === "stop"}
        busy={serviceAction.isPending}
        onCancel={() => setPendingAction(null)}
        onConfirm={() => pendingAction && serviceAction.mutate(pendingAction)}
      />
    </section>
  );
}
