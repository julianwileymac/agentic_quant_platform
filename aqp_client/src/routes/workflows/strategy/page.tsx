import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { PageContainer } from "@/components/shell/PageContainer";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { STRATEGY_NODE_ACCENTS, STRATEGY_PALETTE } from "@/components/strategies/strategyPalette";
import { serializeStrategySpec } from "@/components/strategies/strategySerializer";
import { ApiError, apiFetch } from "@/lib/api/client";

interface PendingSave {
  graph: FlowGraph;
}

export function StrategyComposerRoute() {
  const [name, setName] = useState("composed-strategy");
  const [pending, setPending] = useState<PendingSave | null>(null);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  const submit = async () => {
    if (!pending) return;
    setSaving(true);
    try {
      const spec = serializeStrategySpec(pending.graph, name.trim() || "composed-strategy");
      const res = await apiFetch<{ id?: string; slug?: string }>("/strategies", {
        method: "POST",
        body: JSON.stringify(spec),
      });
      toast.success(`Strategy saved: ${res.slug ?? res.id ?? name}`);
      if (res.id) navigate(`/strategies/${encodeURIComponent(res.id)}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Save failed: ${msg}`);
    } finally {
      setSaving(false);
      setPending(null);
    }
  };

  return (
    <PageContainer
      title="Strategy Composer"
      subtitle="Compose signals + factors + rules + sizing + risk into a registry-style spec persisted to the strategies catalog."
      bleed
    >
      <div className="flex h-[calc(100vh-160px)] flex-col gap-3 px-6 pb-6">
        <div className="flex max-w-md items-center gap-2">
          <Label htmlFor="strategy-name" className="shrink-0">
            Strategy name
          </Label>
          <Input id="strategy-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="min-h-0 flex-1">
          <WorkflowEditor
            domain="strategy"
            paletteSections={STRATEGY_PALETTE}
            accentByKind={STRATEGY_NODE_ACCENTS}
            saving={saving}
            onSave={async (graph) => setPending({ graph })}
          />
        </div>
      </div>

      {pending ? (
        <ConfirmFrictionDialog
          open
          onOpenChange={(open) => !open && setPending(null)}
          title={`Save strategy — ${name}`}
          consequence="Persists the composed spec to the strategies catalog. The spec is registered under the name shown; existing entries with the same slug are versioned."
          details={[
            { label: "Name", value: name },
            { label: "Nodes", value: pending.graph.nodes.length },
            { label: "Edges", value: pending.graph.edges.length },
          ]}
          confirmPhrase=""
          confirmLabel="Save strategy"
          confirmVariant="default"
          onConfirm={submit}
        />
      ) : null}
    </PageContainer>
  );
}
