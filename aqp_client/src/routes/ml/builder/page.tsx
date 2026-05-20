import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { PageContainer } from "@/components/shell/PageContainer";
import { toast } from "@/components/ui/toast";
import { ML_NODE_ACCENTS, ML_PALETTE } from "@/components/ml/mlPalette";
import { serializeMlExperiment } from "@/components/ml/mlSerializer";
import { ApiError, apiFetch } from "@/lib/api/client";

interface PendingSave {
  graph: FlowGraph;
  run: boolean;
}

export function MlBuilderRoute() {
  const [pending, setPending] = useState<PendingSave | null>(null);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  const submit = async () => {
    if (!pending) return;
    setSaving(true);
    try {
      const payload = serializeMlExperiment(pending.graph);
      const res = await apiFetch<{ task_id?: string; id?: string }>("/ml/experiment-runs", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      toast.success(`ML experiment queued: ${res.task_id ?? res.id ?? "ok"}`);
      if (pending.run) navigate("/ml/training");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Submit failed: ${msg}`);
    } finally {
      setSaving(false);
      setPending(null);
    }
  };

  return (
    <PageContainer
      title="ML Builder"
      subtitle="Compose Dataset + Pipeline + Split + Model + Experiment into an /ml/experiment-runs payload."
      bleed
    >
      <div className="flex h-[calc(100vh-160px)] flex-col gap-3 px-6 pb-6">
        <div className="min-h-0 flex-1">
          <WorkflowEditor
            domain="ml"
            paletteSections={ML_PALETTE}
            accentByKind={ML_NODE_ACCENTS}
            saving={saving}
            onSave={async (graph) => setPending({ graph, run: false })}
            onRun={async (graph) => setPending({ graph, run: true })}
          />
        </div>
      </div>

      {pending ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setPending(null)}
          title={pending.run ? "Train ML experiment" : "Save ML spec"}
          consequence={
            pending.run
              ? "POSTs the serialised spec to /ml/experiment-runs which dispatches a training Celery task. The active dataset is loaded into memory; cost grows with handler complexity."
              : "POSTs the serialised spec to /ml/experiment-runs which queues a training task. You can stop / cancel it from the ML Training page."
          }
          details={[
            { label: "Nodes", value: pending.graph.nodes.length },
            { label: "Edges", value: pending.graph.edges.length },
          ]}
          confirmPhrase=""
          confirmLabel={pending.run ? "Train" : "Save and queue"}
          confirmVariant="default"
          onConfirm={submit}
        />
      ) : null}
    </PageContainer>
  );
}
