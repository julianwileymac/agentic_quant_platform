import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Bot, NotebookPen, Save, Workflow } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

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
  kind: z.enum(["trading", "research"]),
  description: z.string().max(280).optional(),
  strategyClass: z.string().min(1, "Strategy class required").max(120),
  strategyModule: z.string().min(1, "Module path required").max(160),
  engine: z.string().min(1, "Engine required").max(80),
  universeSymbols: z.string().min(1, "Symbols required"),
  initialCash: z.coerce.number().positive("Must be positive"),
  maxPositionPct: z.coerce.number().min(0).max(1, "Must be <= 1.0"),
  maxDrawdownPct: z.coerce.number().min(0).max(1, "Must be <= 1.0"),
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
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<BotFormValues>({
    resolver: zodResolver(botFormSchema),
    defaultValues: DEFAULT_VALUES,
  });

  const onSubmit = async (values: BotFormValues) => {
    const symbols = values.universeSymbols
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const spec = {
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
                  <div className="grid grid-cols-2 gap-2">
                    {(["trading", "research"] as const).map((opt) => (
                      <Button
                        key={opt}
                        type="button"
                        variant={field.value === opt ? "default" : "outline"}
                        onClick={() => field.onChange(opt)}
                        className="capitalize"
                      >
                        {opt}
                      </Button>
                    ))}
                  </div>
                )}
              />
            </Field>
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
