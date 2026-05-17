import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ConfirmFrictionDialog } from "@/components/common/ConfirmFrictionDialog";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import type { FlowGraph } from "@/components/flow/types";
import { PageContainer } from "@/components/shell/PageContainer";
import {
  AdvantageEstimatorPicker,
  type AdvantageSelection,
} from "@/components/rl/AdvantageEstimatorPicker";
import {
  BackbonePicker,
  backboneToPolicyKwargs,
  type BackboneSelection,
} from "@/components/rl/BackbonePicker";
import { StopProperlyPenaltyControl } from "@/components/rl/StopProperlyPenaltyControl";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { RL_NODE_ACCENTS, RL_PALETTE } from "@/components/rl/rlPalette";
import { serializeRLExperiment } from "@/components/rl/rlSerializer";
import { ApiError, apiFetch } from "@/lib/api/client";
import { StrategyLibraryApi } from "@/lib/api/strategyLibrary";
import { useTenancyStore } from "@/store/tenancy";

interface PendingSave {
  graph: FlowGraph;
  run: boolean;
}

export function RlLabRoute() {
  const [name, setName] = useState("rl-experiment");
  const [description, setDescription] = useState("");
  const [pending, setPending] = useState<PendingSave | null>(null);
  const [saving, setSaving] = useState(false);
  // Phase D meta-panel state.
  const [backbone, setBackbone] = useState<BackboneSelection | null>(null);
  const [advantage, setAdvantage] = useState<AdvantageSelection | null>(null);
  const [stopProperlyCoef, setStopProperlyCoef] = useState<number | null>(null);
  // Phase D — template deep-link.
  const [searchParams, setSearchParams] = useSearchParams();
  const [templateBanner, setTemplateBanner] = useState<string | null>(null);
  const mode = useTenancyStore((s) => s.mode);
  const navigate = useNavigate();

  useEffect(() => {
    const templateSlug = searchParams.get("template");
    if (!templateSlug) return;
    StrategyLibraryApi.examples().then((res) => {
      const example = res.items.find(
        (it) => it.kind === "rl_spec" && it.slug === templateSlug,
      );
      if (!example) {
        toast.warning(`Template ${templateSlug!} not found in /quant-agents/examples`);
        return;
      }
      const payload = example.payload as Record<string, unknown>;
      const specName = String(payload.name ?? payload.slug ?? templateSlug);
      setName(specName);
      if (typeof payload.description === "string") {
        setDescription(payload.description);
      }
      const training = (payload.training as Record<string, unknown> | undefined) ?? undefined;
      if (training?.stop_properly_penalty_coef !== undefined) {
        setStopProperlyCoef(Number(training.stop_properly_penalty_coef));
      }
      if (training?.advantage && typeof training.advantage === "object") {
        const adv = training.advantage as Record<string, unknown>;
        setAdvantage({
          alias: String(adv.class ?? ""),
          module_path: String(adv.module_path ?? ""),
          kwargs: (adv.kwargs as Record<string, unknown>) ?? {},
        });
      }
      setTemplateBanner(`Hydrated from template ${specName!}`);
      const next = new URLSearchParams(searchParams);
      next.delete("template");
      setSearchParams(next, { replace: true });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async () => {
    if (!pending) return;
    setSaving(true);
    try {
      const spec = serializeRLExperiment(pending.graph, {
        name: name.trim() || "rl-experiment",
        ...(description.trim() ? { description: description.trim() } : {}),
        ...(advantage
          ? {
              advantage: {
                class: advantage.alias,
                module_path: advantage.module_path,
                kwargs: advantage.kwargs,
              },
            }
          : {}),
        ...(stopProperlyCoef !== null
          ? { stop_properly_penalty_coef: stopProperlyCoef }
          : {}),
        ...(backbone
          ? { policy_kwargs: backboneToPolicyKwargs(backbone) }
          : {}),
      });
      const saved = await apiFetch<{ spec_id?: string; spec_hash?: string; name: string }>(
        "/rl/specs",
        { method: "POST", body: JSON.stringify(spec) },
      );
      toast.success(`RL spec saved: ${saved.name}`, {
        description: saved.spec_hash ? `hash ${saved.spec_hash.slice(0, 12)}` : undefined,
      });
      if (pending.run) {
        const res = await apiFetch<{ task_id: string }>("/rl/runs", {
          method: "POST",
          body: JSON.stringify({ application: spec.experiment?.class ?? "default", name: saved.name }),
        });
        toast.success(`RL experiment queued: ${res.task_id}`);
        navigate(`/rl/runs/${res.task_id}`);
      }
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
      title="RL Lab"
      subtitle="Visual composer for an RLExperimentSpec. Save persists an immutable rl_experiment_versions snapshot; Run queues training through RLRuntime."
      extra={<Badge variant={mode === "live" ? "warn" : "secondary"}>{mode}</Badge>}
      bleed
    >
      <div className="flex h-[calc(100vh-160px)] flex-col gap-3 px-6 pb-6">
        {templateBanner ? (
          <Card>
            <CardContent className="py-2 text-xs">
              <Badge variant="secondary" className="mr-2">template</Badge>
              {templateBanner}
            </CardContent>
          </Card>
        ) : null}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="rl-lab-name">Experiment name</Label>
            <Input id="rl-lab-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="rl-lab-desc">Description</Label>
            <Input id="rl-lab-desc" value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Training controls</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 lg:grid-cols-3">
            <BackbonePicker value={backbone} onChange={setBackbone} />
            <AdvantageEstimatorPicker value={advantage} onChange={setAdvantage} />
            <StopProperlyPenaltyControl
              value={stopProperlyCoef}
              onChange={setStopProperlyCoef}
            />
          </CardContent>
        </Card>
        <div className="min-h-0 flex-1">
          <WorkflowEditor
            domain="rl"
            paletteSections={RL_PALETTE}
            accentByKind={RL_NODE_ACCENTS}
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
          title={pending.run ? `Save and run RL experiment — ${name}` : `Save RL spec — ${name}`}
          consequence={
            pending.run
              ? "Persists the spec, then queues training via RLRuntime. Trajectories accrue in rl.trajectories."
              : "Persists an immutable rl_experiment_versions snapshot. Re-snapshotting after edits creates a new version row automatically."
          }
          details={[
            { label: "Name", value: name },
            { label: "Nodes", value: pending.graph.nodes.length },
            { label: "Edges", value: pending.graph.edges.length },
            { label: "Mode", value: mode.toUpperCase(), tone: mode === "live" ? "warn" : "neutral" },
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
