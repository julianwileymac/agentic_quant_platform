import { useCallback, useEffect, useState } from "react";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  controlPlaneApi,
  type ControlPlaneStatus,
  type ControlPlaneTopologyTarget,
} from "@/lib/api/controlPlane";
import { useChatStream } from "@/lib/ws";

export function ControlPlaneKubernetesRoute() {
  const [targets, setTargets] = useState<ControlPlaneTopologyTarget[]>([]);
  const [selectedTarget, setSelectedTarget] = useState("rpi");
  const [status, setStatus] = useState<ControlPlaneStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [confirmDestroy, setConfirmDestroy] = useState(false);
  const stream = useChatStream(taskId, "terraform");

  const activeTarget = targets.find((target) => target.id === selectedTarget);

  const loadTargets = useCallback(async () => {
    try {
      const topology = await controlPlaneApi.getTopology();
      setTargets(topology.targets);
      setSelectedTarget((current) =>
        topology.targets.some((target) => target.id === current)
          ? current
          : (topology.targets.find((target) => target.id === "rpi")?.id ?? topology.targets[0]?.id ?? "local"),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await controlPlaneApi.getTargetStatus(selectedTarget));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [selectedTarget]);

  useEffect(() => {
    void loadTargets();
  }, [loadTargets]);

  useEffect(() => {
    void loadStatus();
    const t = setInterval(loadStatus, 15_000);
    return () => clearInterval(t);
  }, [loadStatus]);

  const deploy = async () => {
    const res = await controlPlaneApi.deployTarget(selectedTarget);
    setTaskId(res.task_id);
  };

  const destroy = async () => {
    setConfirmDestroy(false);
    const res = await controlPlaneApi.destroyTarget(selectedTarget);
    setTaskId(res.task_id);
  };

  return (
    <PageContainer title="Kubernetes Targets" subtitle="Deploy and inspect AQP deployment targets from the centralized topology.">
      {error && <div className="mb-3 rounded border p-2 text-sm text-[var(--neg-fg)]">{error}</div>}
      <Card>
        <CardHeader>
          <CardTitle>Target Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-2">
            {targets.map((target) => (
              <Button
                key={target.id}
                variant={target.id === selectedTarget ? "default" : "outline"}
                onClick={() => setSelectedTarget(target.id)}
              >
                {target.label}
              </Button>
            ))}
          </div>
          <div className="grid gap-2 md:grid-cols-4">
            <Metric label="Adapter" value={String(status?.adapter?.kind ?? activeTarget?.kind ?? "unknown")} />
            <Metric label="Available" value={status?.available ? "yes" : "no"} />
            <Metric label="Pods" value={String(status?.pods?.length ?? 0)} />
            <Metric label="Namespace" value={status?.namespace ?? activeTarget?.namespace ?? "unknown"} />
          </div>
          <div className="flex gap-2">
            <Button onClick={deploy}>Deploy / Apply</Button>
            <Button variant="outline" onClick={() => void controlPlaneApi.restartTarget(selectedTarget)}>Restart API</Button>
            <Button variant="destructive" onClick={() => setConfirmDestroy(true)}>Destroy</Button>
          </div>
          {taskId && (
            <div className="rounded border p-2 font-mono text-xs">
              <div>task: {taskId}</div>
              {stream.events.map((event) => (
                <div key={`${String(event.timestamp ?? "")}:${String(event.stage ?? "")}:${String(event.message ?? "")}`}>
                  [{String(event.stage ?? "running")}] {String(event.message ?? "")}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
      {confirmDestroy && (
        <ConfirmFrictionDialog
          open={confirmDestroy}
          onOpenChange={setConfirmDestroy}
          title={`Destroy ${activeTarget?.label ?? selectedTarget} AQP deployment`}
          consequence={`This dispatches Terraform destroy for the ${activeTarget?.label ?? selectedTarget} AQP stack.`}
          confirmPhrase="DESTROY"
          confirmLabel={`Destroy ${activeTarget?.label ?? selectedTarget} deployment`}
          confirmVariant="destructive"
          onConfirm={destroy}
        />
      )}
    </PageContainer>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border p-2">
      <div className="text-xs uppercase text-[var(--text-secondary)]">{label}</div>
      <div className="font-mono">{value}</div>
    </div>
  );
}
