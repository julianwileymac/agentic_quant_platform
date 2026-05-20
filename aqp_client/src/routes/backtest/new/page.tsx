import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, PlayCircle } from "lucide-react";
import { useMemo } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { PageContainer } from "@/components/shell/PageContainer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/client";
import { BacktestApi } from "@/lib/api/backtest";
import { cn } from "@/lib/utils";

const formSchema = z.object({
  runName: z.string().min(1).max(80),
  strategyClass: z.string().min(1),
  strategyModule: z.string().min(1),
  symbols: z.string().min(1, "At least one symbol"),
  start: z.string().min(1),
  end: z.string().min(1),
  initialCash: z.coerce.number().positive(),
  kwargs: z.string().refine(
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

type Values = z.infer<typeof formSchema>;

const DEFAULTS: Values = {
  runName: "backtest-new",
  strategyClass: "FrameworkAlgorithm",
  strategyModule: "aqp.strategies.framework",
  symbols: "AAPL.NASDAQ, MSFT.NASDAQ, SPY.NASDAQ",
  start: "2022-01-01",
  end: "2024-12-31",
  initialCash: 100_000,
  kwargs: `{\n  "alpha_model": {\n    "class": "MeanReversionAlpha",\n    "module_path": "aqp.strategies.mean_reversion",\n    "kwargs": {"lookback": 20, "z_threshold": 2.0}\n  }\n}`,
};

/**
 * When the Agent Templates Gallery deep-links here with ``?agent=<spec>``
 * the spec is preselected on the backtest. The strategy class is held
 * fixed (``FrameworkAlgorithm`` is the agent-aware shell that drives a
 * spec at every bar) and the chosen ``AgentSpec`` is wired in via
 * ``kwargs.agent_spec`` so the backtest task can dispatch the right
 * runtime invocation.
 */
function valuesWithAgent(agentSpec: string | null): Values {
  if (!agentSpec) return DEFAULTS;
  const kwargsObj = {
    agent_spec: { name: agentSpec },
    alpha_model: {
      class: "AgenticAlphaShell",
      module_path: "aqp.strategies.agentic.agent_alpha",
      kwargs: { spec_name: agentSpec },
    },
  };
  return {
    ...DEFAULTS,
    runName: `backtest-${agentSpec.replace(/[^a-zA-Z0-9._-]+/g, "-")}`,
    kwargs: JSON.stringify(kwargsObj, null, 2),
  };
}

export function BacktestNewRoute() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const agentSpec = searchParams.get("agent");
  const defaults = useMemo(() => valuesWithAgent(agentSpec), [agentSpec]);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    control,
  } = useForm<Values>({ resolver: zodResolver(formSchema), defaultValues: defaults });

  const onSubmit = async (v: Values) => {
    const symbols = v.symbols.split(",").map((s) => s.trim()).filter(Boolean);
    let extraKwargs: Record<string, unknown> = {};
    if (v.kwargs.trim()) {
      try {
        extraKwargs = JSON.parse(v.kwargs) as Record<string, unknown>;
      } catch {
        toast.error("kwargs JSON is invalid");
        return;
      }
    }
    const strategy = {
      class: v.strategyClass,
      module_path: v.strategyModule,
      kwargs: {
        universe_model: {
          class: "StaticUniverse",
          module_path: "aqp.strategies.universes",
          kwargs: { symbols },
        },
        ...extraKwargs,
      },
    };
    try {
      const res = await BacktestApi.start({
        strategy,
        run_name: v.runName,
        session: { initial_cash: v.initialCash, start: v.start, end: v.end },
      });
      toast.success(`Backtest queued: ${res.task_id}`);
      navigate(`/backtest/${res.task_id}`);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      toast.error(`Submit failed: ${msg}`);
    }
  };

  return (
    <PageContainer
      title="New backtest"
      subtitle={
        agentSpec
          ? `Spec ${agentSpec} preloaded from Agent Templates — kwargs prefilled to drive the AgenticAlphaShell.`
          : "Compose a one-off backtest. Bot-scoped backtests live under each bot's detail page."
      }
      extra={
        <div className="flex items-center gap-2">
          {agentSpec ? (
            <Badge variant="outline" className="font-mono text-xs">
              agent: {agentSpec}
            </Badge>
          ) : null}
          <Button asChild variant="ghost" size="sm">
            <Link to="/backtest">
              <ArrowLeft className="h-4 w-4" /> All runs
            </Link>
          </Button>
        </div>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Identity</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Field label="Run name" error={errors.runName?.message}>
              <Input {...register("runName")} autoFocus />
            </Field>
            <Field label="Strategy class" error={errors.strategyClass?.message}>
              <Input className="font-mono" {...register("strategyClass")} />
            </Field>
            <Field label="Module path" error={errors.strategyModule?.message}>
              <Input className="font-mono" {...register("strategyModule")} />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Universe + window</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Field label="Symbols (comma-separated)" error={errors.symbols?.message}>
              <Input className="font-mono" {...register("symbols")} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Start" error={errors.start?.message}>
                <Input type="date" {...register("start")} />
              </Field>
              <Field label="End" error={errors.end?.message}>
                <Input type="date" {...register("end")} />
              </Field>
            </div>
            <Field label="Initial cash" error={errors.initialCash?.message}>
              <Input type="number" step="1000" className="font-mono" {...register("initialCash")} />
            </Field>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Strategy kwargs (JSON)</CardTitle>
          </CardHeader>
          <CardContent>
            <Controller
              control={control}
              name="kwargs"
              render={({ field }) => (
                <textarea
                  {...field}
                  rows={10}
                  className={cn(
                    "w-full resize-y rounded-md border border-[var(--border-default)] bg-[var(--bg-app)] p-3 font-mono text-xs",
                    errors.kwargs && "border-[var(--neg-fg)]",
                  )}
                />
              )}
            />
            {errors.kwargs ? (
              <p className="mt-1 text-xs text-[var(--neg-fg)]">{errors.kwargs.message}</p>
            ) : null}
          </CardContent>
        </Card>

        <div className="lg:col-span-2 flex items-center gap-2">
          <Button type="submit" disabled={isSubmitting} className="gap-2">
            <PlayCircle className="h-4 w-4" /> {isSubmitting ? "Submitting…" : "Run backtest"}
          </Button>
          <span className="text-xs text-[var(--text-secondary)]">
            POSTs to <code className="font-mono">/backtest/runs</code>; you'll be redirected to the
            detail page on the returned task_id.
          </span>
        </div>
      </form>
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
