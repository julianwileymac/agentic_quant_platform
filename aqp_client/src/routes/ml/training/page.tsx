import { zodResolver } from "@hookform/resolvers/zod";
import { Brain, PlayCircle, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { DataTable } from "@/components/common/DataTable";
import { Numeric } from "@/components/common/Numeric";
import { ProgressTimeline } from "@/components/common/ProgressTimeline";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { MlApi, type MlDataset, type MlRunSummary } from "@/lib/api/ml";
import { useChatStream } from "@/lib/ws";
import { cn, formatTime } from "@/lib/utils";

const trainSchema = z.object({
  modelKind: z.string().min(1),
  datasetId: z.string().optional(),
  features: z.string().optional(),
  target: z.string().optional(),
  runName: z.string().optional(),
  hyperparams: z.string().refine(
    (v) => {
      if (!v.trim()) return true;
      try {
        JSON.parse(v);
        return true;
      } catch {
        return false;
      }
    },
    { message: "Must be valid JSON" },
  ),
});

type TrainValues = z.infer<typeof trainSchema>;

const STARTER_HYPERPARAMS = `{\n  "n_estimators": 200,\n  "max_depth": 6,\n  "learning_rate": 0.05\n}`;

export function MlTrainingRoute() {
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const stream = useChatStream(activeTaskId, "chat");

  const runs = useApiQuery<MlRunSummary[]>({
    queryKey: ["ml", "runs"],
    path: "/ml/runs",
    refetchInterval: 5_000,
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });
  const datasets = useApiQuery<MlDataset[]>({
    queryKey: ["ml", "datasets"],
    path: "/ml/datasets",
    select: (raw) => (Array.isArray(raw) ? raw : []),
  });

  const activeRuns = useMemo(
    () => (runs.data ?? []).filter((r) => r.status === "running" || r.status === "queued"),
    [runs.data],
  );

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<TrainValues>({
    resolver: zodResolver(trainSchema),
    defaultValues: {
      modelKind: "lightgbm",
      runName: "ml-training-run",
      hyperparams: STARTER_HYPERPARAMS,
    },
  });

  const onSubmit = async (v: TrainValues) => {
    let hyperparams: Record<string, unknown> | undefined;
    if (v.hyperparams.trim()) {
      try {
        hyperparams = JSON.parse(v.hyperparams) as Record<string, unknown>;
      } catch {
        toast.error("Invalid hyperparams JSON");
        return;
      }
    }
    const features = v.features?.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      const res = await MlApi.train({
        model_kind: v.modelKind,
        dataset_id: v.datasetId,
        features,
        target: v.target,
        hyperparams,
        run_name: v.runName,
      });
      toast.success(`Training queued: ${res.task_id}`);
      setActiveTaskId(res.task_id);
      runs.refetch();
      reset({ ...v });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Training submit failed: ${msg}`);
    }
  };

  return (
    <PageContainer
      title="ML Training"
      subtitle="Train models with the AlphaBacktestExperiment / workbench-flow runners. Progress streams over /chat/stream/{task_id}."
      extra={
        <Button variant="ghost" size="sm" onClick={() => runs.refetch()}>
          <RefreshCcw className="h-4 w-4" /> Refresh
        </Button>
      }
    >
      <Tabs defaultValue="runs">
        <TabsList>
          <TabsTrigger value="runs">Runs ({runs.data?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="train">Train new</TabsTrigger>
          <TabsTrigger value="progress">Progress ({activeRuns.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="runs">
          <Card className="h-[calc(100vh-260px)]">
            <CardContent className="h-full p-0">
              <DataTable<MlRunSummary>
                rows={runs.data ?? []}
                rowKey={(r) => r.id}
                onRowClick={(r) => r.task_id && setActiveTaskId(r.task_id)}
                emptyState={
                  <div className="flex flex-col items-center gap-2">
                    <Brain className="h-6 w-6" />
                    <span>No training runs yet.</span>
                  </div>
                }
                columns={[
                  {
                    key: "name",
                    header: "Run",
                    render: (r) => (
                      <div className="flex flex-col">
                        <span className="font-medium">{r.run_name ?? r.id}</span>
                        <span className="font-mono text-[10px] text-[var(--text-muted)]">{r.id}</span>
                      </div>
                    ),
                  },
                  {
                    key: "model_kind",
                    header: "Model",
                    width: 130,
                    render: (r) => <Badge variant="secondary">{r.model_kind ?? "—"}</Badge>,
                  },
                  {
                    key: "status",
                    header: "Status",
                    width: 110,
                    render: (r) => (
                      <Badge
                        variant={
                          r.status === "completed"
                            ? "positive"
                            : r.status === "running" || r.status === "queued"
                              ? "default"
                              : r.status === "failed"
                                ? "negative"
                                : "secondary"
                        }
                      >
                        {r.status ?? "—"}
                      </Badge>
                    ),
                  },
                  {
                    key: "rmse",
                    header: "RMSE",
                    width: 110,
                    align: "right",
                    render: (r) => <Numeric value={r.rmse ?? null} kind="decimal" digits={6} color="force-neg" />,
                  },
                  {
                    key: "mae",
                    header: "MAE",
                    width: 110,
                    align: "right",
                    render: (r) => <Numeric value={r.mae ?? null} kind="decimal" digits={6} color="force-neg" />,
                  },
                  {
                    key: "r2",
                    header: "R²",
                    width: 90,
                    align: "right",
                    render: (r) => <Numeric value={r.r2 ?? null} kind="decimal" digits={3} color="auto" />,
                  },
                  {
                    key: "started_at",
                    header: "Started",
                    width: 130,
                    align: "right",
                    render: (r) => (
                      <span className="text-[var(--text-secondary)]">
                        {r.started_at ? formatTime(r.started_at) : "—"}
                      </span>
                    ),
                  },
                ]}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="train">
          <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Identity</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3">
                <Field label="Model kind" error={errors.modelKind?.message}>
                  <Input className="font-mono" {...register("modelKind")} />
                </Field>
                <Field label="Run name" error={errors.runName?.message}>
                  <Input {...register("runName")} />
                </Field>
                <Field label="Dataset id (optional)">
                  <Input list="ml-datasets-list" className="font-mono" {...register("datasetId")} />
                  <datalist id="ml-datasets-list">
                    {(datasets.data ?? []).map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </datalist>
                </Field>
                <Field label="Features (comma-separated)">
                  <Input className="font-mono" {...register("features")} />
                </Field>
                <Field label="Target column">
                  <Input className="font-mono" {...register("target")} />
                </Field>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Hyperparams (JSON)</CardTitle>
              </CardHeader>
              <CardContent>
                <Controller
                  control={control}
                  name="hyperparams"
                  render={({ field }) => (
                    <textarea
                      {...field}
                      rows={12}
                      className={cn(
                        "w-full resize-y rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs",
                        errors.hyperparams && "border-[var(--neg-fg)]",
                      )}
                    />
                  )}
                />
                {errors.hyperparams ? (
                  <p className="mt-1 text-xs text-[var(--neg-fg)]">{errors.hyperparams.message}</p>
                ) : null}
              </CardContent>
            </Card>

            <div className="lg:col-span-2 flex items-center gap-2">
              <Button type="submit" disabled={isSubmitting} className="gap-2">
                <PlayCircle className="h-4 w-4" /> {isSubmitting ? "Submitting…" : "Train model"}
              </Button>
            </div>
          </form>
        </TabsContent>

        <TabsContent value="progress">
          <Card>
            <CardHeader>
              <CardTitle>Active training runs</CardTitle>
              <Badge variant="secondary">{activeRuns.length}</Badge>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
                <div className="flex flex-col gap-1">
                  {activeRuns.length === 0 ? (
                    <p className="text-xs text-[var(--text-secondary)]">No active runs.</p>
                  ) : (
                    activeRuns.map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        onClick={() => r.task_id && setActiveTaskId(r.task_id)}
                        className={cn(
                          "flex flex-col items-start rounded-md border border-[var(--border-default)] px-3 py-2 text-left transition-colors hover:bg-[var(--bg-elevated)]",
                          activeTaskId === r.task_id && "bg-[var(--info-bg)] text-[var(--info-fg)]",
                        )}
                      >
                        <span className="text-xs font-medium">{r.run_name ?? r.id}</span>
                        <span className="font-mono text-[10px] text-[var(--text-muted)]">{r.task_id ?? "—"}</span>
                      </button>
                    ))
                  )}
                </div>
                <ProgressTimeline events={stream.events} height={400} follow />
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageContainer>
  );
}

function Field({ label, error, children }: { label: string; error?: string | undefined; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <Label>{label}</Label>
      {children}
      {error ? <span className="text-xs text-[var(--neg-fg)]">{error}</span> : null}
    </div>
  );
}
