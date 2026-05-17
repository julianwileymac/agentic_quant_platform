import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Bot, NotebookPen, Save, Workflow } from "lucide-react";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { EntityPicker } from "@/components/common/EntityPicker";
import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { BotsApi } from "@/lib/api/bots";
import { cn } from "@/lib/utils";

const botFormSchema = z.object({
  name: z.string().min(2, "Name is required").max(80),
  // Hybrid agentic-RL Phase 8: RLTradingBot expands the kind enum
  // so the form can wire `BotSpec.rl_experiment_ref` for bots driven
  // by a trained RL policy.
  kind: z.enum(["trading", "research", "rl_trading"]),
  description: z.string().max(280).optional(),
  strategyClass: z.string().min(1, "Strategy class required").max(120),
  strategyModule: z.string().min(1, "Module path required").max(160),
  engine: z.string().min(1, "Engine required").max(80),
  universeSymbols: z.string().min(1, "Symbols required"),
  initialCash: z.coerce.number().positive("Must be positive"),
  maxPositionPct: z.coerce.number().min(0).max(1, "Must be <= 1.0"),
  maxDrawdownPct: z.coerce.number().min(0).max(1, "Must be <= 1.0"),
  // Optional RL experiment reference — only populated when kind=rl_trading.
  rlExperimentSlug: z.string().max(120).optional(),
  rlCheckpoint: z.string().max(500).optional(),
});

type BotFormValues = z.infer<typeof botFormSchema>;

const DEFAULT_VALUES: BotFormValues = {
  name: "mean-rev-bot",
  kind: "trading",
  description: "Mean-reversion bot driven by AgentRuntime hints.",
  strategyClass: "FrameworkAlgorithm",
  strategyModule: "aqp.strategies.framework",
  engine: "vbt-pro",
  universeSymbols: "AAPL.NASDAQ, MSFT.NASDAQ, SPY.NASDAQ",
  initialCash: 100_000,
  maxPositionPct: 0.1,
  maxDrawdownPct: 0.2,
};

export function BotNewRoute() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    register,
    handleSubmit,
    control,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<BotFormValues>({
    resolver: zodResolver(botFormSchema),
    defaultValues: DEFAULT_VALUES,
  });

  // Phase E deep-link: ``?rl_experiment=<slug>&checkpoint=<path>``
  // (used by gallery "Use as template" cards for ``rl_spec`` examples
  // that want to bootstrap a bot directly).
  useEffect(() => {
    const slug = searchParams.get("rl_experiment");
    const checkpoint = searchParams.get("checkpoint");
    if (!slug && !checkpoint) return;
    setValue("kind", "rl_trading");
    if (slug) setValue("rlExperimentSlug", slug);
    if (checkpoint) setValue("rlCheckpoint", checkpoint);
    const next = new URLSearchParams(searchParams);
    next.delete("rl_experiment");
    next.delete("checkpoint");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSubmit = async (values: BotFormValues) => {
    const symbols = values.universeSymbols
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const spec: Record<string, unknown> = {
      name: values.name,
      kind: values.kind,
      description: values.description ?? undefined,
      strategy: {
        class: values.strategyClass,
        module_path: values.strategyModule,
        kwargs: {
          universe_model: {
            class: "StaticUniverse",
            module_path: "aqp.strategies.universes",
            kwargs: { symbols },
          },
        },
      },
      engine: { kind: values.engine },
      session: {
        initial_cash: values.initialCash,
      },
      risk: {
        max_position_pct: values.maxPositionPct,
        max_drawdown_pct: values.maxDrawdownPct,
      },
    };
    // Hybrid agentic-RL Phase 8: attach the rl_experiment_ref when
    // the user picked rl_trading. The backend BotRuntime then routes
    // the lifecycle through RLRuntime instead of the engine factory.
    if (values.kind === "rl_trading" && values.rlExperimentSlug) {
      spec.rl_experiment_ref = {
        slug: values.rlExperimentSlug,
        checkpoint: values.rlCheckpoint || undefined,
        deterministic: true,
      };
    }
    try {
      const created = await BotsApi.create(spec);
      toast.success(`Bot ${created.name} created`);
      navigate(`/bots/${created.id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Create failed: ${msg}`);
    }
  };

  return (
    <PageContainer
      title="New Bot"
      subtitle="Compose a TradingBot or ResearchBot. The visual builder lands in Phase 4 — this form ships a complete spec today."
      extra={
        <Badge variant="warn" className="gap-2">
          <Workflow className="h-3 w-3" /> Visual builder: Phase 4
        </Badge>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-4 w-4" /> Identity
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Field label="Name" error={errors.name?.message}>
              <Input id="bot-name" {...register("name")} autoFocus />
            </Field>
            <Field label="Kind" error={errors.kind?.message}>
              <Controller
                control={control}
                name="kind"
                render={({ field }) => (
                  <div className="grid grid-cols-3 gap-2">
                    {(["trading", "research", "rl_trading"] as const).map((opt) => (
                      <Button
                        key={opt}
                        type="button"
                        variant={field.value === opt ? "default" : "outline"}
                        onClick={() => field.onChange(opt)}
                        className="capitalize"
                      >
                        {opt.replace("_", " ")}
                      </Button>
                    ))}
                  </div>
                )}
              />
            </Field>
            <Controller
              control={control}
              name="kind"
              render={({ field }) =>
                field.value === "rl_trading" ? (
                  <div className="grid gap-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
                    <p className="text-xs text-muted-foreground">
                      RL trading bots route lifecycle (backtest / paper) through
                      <code className="mx-1 rounded bg-muted px-1">RLRuntime</code>
                      instead of the standard engine factory. Pin the trained
                      RLExperimentSpec slug here.
                    </p>
                    <Field label="RL experiment slug" error={errors.rlExperimentSlug?.message}>
                      <Controller
                        control={control}
                        name="rlExperimentSlug"
                        render={({ field: pickField }) => (
                          <EntityPicker
                            kind="rl_experiments"
                            value={pickField.value ?? null}
                            onChange={(v) => pickField.onChange(v ?? "")}
                            placeholder="Pick a registered RL experiment..."
                            allowCustom
                          />
                        )}
                      />
                    </Field>
                    <Field label="Checkpoint (optional)" error={errors.rlCheckpoint?.message}>
                      <Input
                        id="rl-checkpoint"
                        className="font-mono"
                        placeholder="data/models/rl/<run>/policy.zip"
                        {...register("rlCheckpoint")}
                      />
                    </Field>
                  </div>
                ) : (
                  <></>
                )
              }
            />
            <Field label="Description (optional)" error={errors.description?.message}>
              <Input id="bot-description" {...register("description")} />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <NotebookPen className="h-4 w-4" /> Strategy
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Field label="Strategy class" error={errors.strategyClass?.message}>
              <Input id="strategy-class" className="font-mono" {...register("strategyClass")} />
            </Field>
            <Field label="Module path" error={errors.strategyModule?.message}>
              <Input id="strategy-module" className="font-mono" {...register("strategyModule")} />
            </Field>
            <Field label="Engine" error={errors.engine?.message}>
              <Input id="engine" className="font-mono" {...register("engine")} />
            </Field>
            <Field label="Universe symbols (comma-separated)" error={errors.universeSymbols?.message}>
              <Input id="universe" className="font-mono" {...register("universeSymbols")} />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Capital + risk</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <Field label="Initial cash" error={errors.initialCash?.message}>
              <Input
                id="initial-cash"
                type="number"
                step="1000"
                className="font-mono"
                {...register("initialCash")}
              />
            </Field>
            <Field label="Max position % NAV" error={errors.maxPositionPct?.message}>
              <Input
                id="max-pos"
                type="number"
                step="0.01"
                className="font-mono"
                {...register("maxPositionPct")}
              />
            </Field>
            <Field label="Max drawdown % NAV" error={errors.maxDrawdownPct?.message}>
              <Input
                id="max-dd"
                type="number"
                step="0.01"
                className="font-mono"
                {...register("maxDrawdownPct")}
              />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Submit</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm text-[var(--text-secondary)]">
            <p>
              Submitting POSTs the spec to{" "}
              <code className="rounded bg-[var(--bg-app)] px-1 font-mono">/bots</code>. The server
              hashes the spec and persists an immutable{" "}
              <code className="rounded bg-[var(--bg-app)] px-1 font-mono">bot_versions</code> row.
              Lifecycle actions (backtest / paper / deploy) are available on the bot detail page.
            </p>
            <div className="flex items-center gap-2">
              <Button type="submit" disabled={isSubmitting} className="gap-2">
                <Save className="h-4 w-4" /> {isSubmitting ? "Saving…" : "Save bot"}
              </Button>
              <Button asChild variant="outline">
                <Link to="/bots/builder">
                  <ArrowRight className="h-4 w-4" /> Open visual builder
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </form>
    </PageContainer>
  );
}

interface FieldProps {
  label: string;
  error?: string | undefined;
  children: React.ReactNode;
}

function Field({ label, error, children }: FieldProps) {
  return (
    <div className={cn("flex flex-col gap-1", error && "[&_input]:border-[var(--neg-fg)]")}>
      <Label>{label}</Label>
      {children}
      {error ? <span className="text-xs text-[var(--neg-fg)]">{error}</span> : null}
    </div>
  );
}
