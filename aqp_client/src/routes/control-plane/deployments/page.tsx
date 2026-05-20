import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  controlPlaneApi,
  type ControlPlaneStatus,
  type ControlPlaneTopologyTarget,
} from "@/lib/api/controlPlane";

export function ControlPlaneDeploymentsRoute() {
  const [targets, setTargets] = useState<ControlPlaneTopologyTarget[]>([]);
  const [selectedTarget, setSelectedTarget] = useState("rpi");
  const [status, setStatus] = useState<ControlPlaneStatus | null>(null);

  useEffect(() => {
    void controlPlaneApi.getTopology().then((topology) => {
      setTargets(topology.targets);
      const defaultTarget = topology.targets.find((target) => target.id === "rpi") ?? topology.targets[0];
      if (defaultTarget) {
        setSelectedTarget(defaultTarget.id);
      }
    });
  }, []);

  useEffect(() => {
    void controlPlaneApi.getTargetStatus(selectedTarget).then(setStatus).catch(() => setStatus(null));
  }, [selectedTarget]);

  const activeTarget = targets.find((target) => target.id === selectedTarget);
  const services = status?.services ?? activeTarget?.services ?? [];

  return (
    <PageContainer title="Deployment Topology" subtitle="AQP service topology from the centralized deployment manifest.">
      <div className="mb-3 flex flex-wrap gap-2">
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
      <div className="grid gap-3 md:grid-cols-3">
        {services.map((svc) => {
          const podCount = status?.pods.filter((p) => String((p.labels as Record<string, unknown> | undefined)?.app ?? "") === svc.app_label).length ?? 0;
          return (
            <Card key={svc.id}>
              <CardHeader><CardTitle className="font-mono text-sm">{svc.id}</CardTitle></CardHeader>
              <CardContent className="text-sm text-[var(--text-secondary)]">
                <div>{svc.label}</div>
                <div>role: <span className="font-mono text-[var(--text-primary)]">{svc.role}</span></div>
                <div>workload: <span className="font-mono text-[var(--text-primary)]">{svc.workload}</span></div>
                <div>pods: <span className="font-mono text-[var(--text-primary)]">{podCount}</span></div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </PageContainer>
  );
}
