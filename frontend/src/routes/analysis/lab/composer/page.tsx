import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  buildAccentMap,
  buildAnalysisPalette,
} from "@/components/analysis/analysisPalette";
import { serializeAnalysisSpec } from "@/components/analysis/analysisSerializer";
import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import {
  type FlowSchema,
  listAnalysisFlows,
  runAnalysisSpec,
  saveAnalysisSpec,
} from "@/lib/analysis/api";
import { ApiError } from "@/lib/api/client";

interface Pending {
  graph: FlowGraph;
  run: boolean;
}

export function AnalysisComposerRoute() {
  const [name, setName] = useState("analysis-spec");
  const [description, setDescription] = useState("");
  const [dataset, setDataset] = useState("");
  const [dataOwner, setDataOwner] = useState("research-team");
  const [semantic, setSemantic] = useState("Multi-step analysis pipeline");
  const [flows, setFlows] = useState<FlowSchema[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    listAnalysisFlows().then((res) => {
      if (!cancelled) setFlows(res);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const palette = useMemo(() => buildAnalysisPalette(flows), [flows]);
  const accents = useMemo(() => buildAccentMap(flows), [flows]);

  const submit = async () => {
    if (!pending) return;
    setSaving(true);
    try {
      const slug = (name.trim() || "analysis-spec")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
      const trimmedDescription = description.trim();
      const spec = serializeAnalysisSpec(pending.graph, {
        name: name.trim() || "analysis-spec",
        ...(trimmedDescription ? { description: trimmedDescription } : {}),
        dataset: { iceberg_identifier: dataset.trim() },
        data_owner: dataOwner.trim() || "research-team",
        semantic_definition:
          semantic.trim() || "Multi-step analysis pipeline (Composer)",
        domain: "research.analysis_lab",
      });
      const saved = await saveAnalysisSpec(spec as unknown as Record<string, unknown>);
      toast.success(`Analysis spec saved: ${saved.name}`, {
        description: `version ${saved.current_version}`,
      });
      if (pending.run) {
        const res = await runAnalysisSpec(slug, "run");
        toast.success(`Analysis run queued: ${res.task_id}`);
        navigate("/analysis/runs");
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Composer submit failed: ${msg}`);
    } finally {
      setSaving(false);
      setPending(null);
    }
  };

  return (
    <PageContainer
      title="Analysis Composer"
      subtitle="Drag analysis nodes onto the canvas, save persists an immutable analysis_spec_versions snapshot, run drives AnalysisRuntime."
      extra={<Badge variant="secondary">{flows.length} flows</Badge>}
      bleed
    >
      <div className="flex h-[calc(100vh-160px)] flex-col gap-3 px-6 pb-6">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-4">
          <div className="flex flex-col gap-1">
            <Label htmlFor="composer-name">Spec name</Label>
            <Input
              id="composer-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="composer-description">Description</Label>
            <Input
              id="composer-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="composer-dataset">Iceberg dataset</Label>
            <Input
              id="composer-dataset"
              placeholder="aqp_silver_yfinance.equities_daily"
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-1">
            <div className="flex flex-col gap-1">
              <Label htmlFor="composer-owner">Data owner</Label>
              <Input
                id="composer-owner"
                value={dataOwner}
                onChange={(e) => setDataOwner(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="composer-semantic">Semantic</Label>
              <Input
                id="composer-semantic"
                value={semantic}
                onChange={(e) => setSemantic(e.target.value)}
              />
            </div>
          </div>
        </div>
        <div className="min-h-0 flex-1">
          <WorkflowEditor
            domain="analysis"
            paletteSections={palette}
            accentByKind={accents}
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
          title={pending.run ? `Save and run analysis — ${name}` : `Save analysis spec — ${name}`}
          consequence={
            pending.run
              ? "Persists the spec, then queues AnalysisRuntime.run via the agents queue. Each step's gold-tier output lands under aqp_gold_analysis_<namespace>."
              : "Persists an immutable analysis_spec_versions snapshot. Re-snapshotting after edits creates a new version row automatically."
          }
          details={[
            { label: "Name", value: name },
            { label: "Dataset", value: dataset || "(unset)" },
            { label: "Nodes", value: pending.graph.nodes.length },
            { label: "Edges", value: pending.graph.edges.length },
          ]}
          confirmPhrase=""
          confirmLabel={pending.run ? "Save and queue" : "Save spec"}
          confirmVariant="default"
          onConfirm={submit}
        />
      ) : null}
    </PageContainer>
  );
}
