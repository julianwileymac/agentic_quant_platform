import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { listPods, type PodInfo } from "@/lib/api/clusterPods";

/**
 * Cluster pod browser — backs `/cluster/pods/*` (Phase F of the
 * Management Engine plan). Live exec + log tail use xterm.js + the
 * existing WebSocket helpers; the initial drop ships the inventory
 * surface so operators can find the right pod before opening a
 * terminal.
 */
export function ClusterMgmtRoute(): React.ReactElement {
  const [namespace, setNamespace] = useState("aqp");
  const [labelSelector, setLabelSelector] = useState("");

  const { data: pods = [], isLoading, error } = useQuery({
    queryKey: ["cluster-mgmt", "pods", namespace, labelSelector],
    queryFn: () => listPods(namespace, labelSelector || undefined),
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Cluster pods</h1>
        <p className="text-muted-foreground text-sm">
          Inventory backed by the active <code>KubernetesAdapter</code>.
          Exec / log tail land in the next milestone — Phase F-2.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm">
          <span className="block text-muted-foreground">Namespace</span>
          <input
            value={namespace}
            onChange={(e) => setNamespace(e.target.value)}
            className="w-48 rounded border border-input bg-transparent px-2 py-1 text-sm font-mono"
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="block text-muted-foreground">Label selector</span>
          <input
            placeholder="e.g. app=aqp-api"
            value={labelSelector}
            onChange={(e) => setLabelSelector(e.target.value)}
            className="w-64 rounded border border-input bg-transparent px-2 py-1 text-sm font-mono"
          />
        </label>
      </div>

      {error && (
        <Card className="border-destructive bg-destructive/10 p-4">
          <p className="text-destructive text-sm">Failed to load pods: {String(error)}</p>
        </Card>
      )}

      {isLoading ? (
        <p className="text-muted-foreground">Loading pods…</p>
      ) : (
        <div className="grid gap-3">
          {pods.map((pod) => (
            <PodRow key={`${pod.namespace}/${pod.name}`} pod={pod} />
          ))}
          {pods.length === 0 && !isLoading && (
            <p className="text-muted-foreground text-sm">
              No pods returned. Check the namespace + label selector, or confirm the
              active KubernetesAdapter is configured.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function PodRow({ pod }: { pod: PodInfo }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono font-medium">{pod.name}</span>
            <Badge variant="outline">ns: {pod.namespace}</Badge>
            <Badge
              variant={pod.phase.toLowerCase() === "running" ? "default" : "secondary"}
            >
              {pod.phase || "unknown"}
            </Badge>
            {pod.node && (
              <Badge variant="secondary">node: {pod.node}</Badge>
            )}
          </div>
          {pod.containers.length > 0 && (
            <p className="mt-1 text-muted-foreground text-xs font-mono">
              containers: {pod.containers.join(", ")}
            </p>
          )}
          {pod.pod_ip && (
            <p className="text-muted-foreground text-xs font-mono tabular-nums">
              ip: {pod.pod_ip}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-2">
          <Button size="sm" variant="outline" disabled>
            Exec (Phase F-2)
          </Button>
          <Button size="sm" variant="outline" disabled>
            Logs (Phase F-2)
          </Button>
        </div>
      </div>
    </Card>
  );
}
