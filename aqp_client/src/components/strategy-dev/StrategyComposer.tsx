import { Library, Loader2, Plus, Save, PlayCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { CodeEditor } from "@/components/common/CodeEditor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "@/components/ui/toast";
import { ApiError, apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

import { useStrategyDev } from "./StrategyDevLayout";

interface StrategyComponentRow {
  /** Registered alias. */
  name: string;
  /** Registry kind: `strategy` / `alpha` / `risk` / `portfolio` / etc. */
  kind: string;
  module_path: string;
  source?: string | null;
  category?: string | null;
  tags?: string[];
  description?: string | null;
}

interface ComponentsResponse {
  components: StrategyComponentRow[];
}

const DEFAULT_YAML = `# Strategy YAML — composed via the strategy composer.
# Edit freely, drag a component from the palette to insert a stub.
name: my-strategy
class: FrameworkAlgorithm
module_path: aqp.strategies.framework
kwargs:
  alpha:
    class: MomentumAlpha
    module_path: aqp.strategies.momentum
    kwargs: {}
  risk:
    class: BasicRiskModel
    module_path: aqp.strategies.risk
    kwargs:
      max_drawdown: 0.15
  portfolio:
    class: EqualWeightPortfolio
    module_path: aqp.strategies.portfolio_construction
    kwargs: {}
  execution:
    class: MarketOrderExecution
    module_path: aqp.strategies.execution
    kwargs: {}
  universe:
    class: StaticUniverse
    module_path: aqp.strategies.universes
    kwargs:
      symbols: ["AAPL", "MSFT"]
`;

const KIND_GROUPS: { key: string; label: string }[] = [
  { key: "strategy", label: "Strategies" },
  { key: "alpha", label: "Alphas" },
  { key: "portfolio", label: "Portfolio" },
  { key: "risk", label: "Risk" },
  { key: "execution", label: "Execution" },
  { key: "universe", label: "Universe" },
];

/**
 * YAML-first strategy composer. The palette lists every `@register`ed
 * component grouped by `kind` and supports drag-into-editor by clicking
 * "Add". Final YAML can be saved to the strategy library or routed to
 * the simulation creator.
 */
export function StrategyComposer() {
  const navigate = useNavigate();
  const { selection, setSelection } = useStrategyDev();
  const [yaml, setYaml] = useState<string>(selection.composerYaml || DEFAULT_YAML);
  const [strategyName, setStrategyName] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tab, setTab] = useState<string>(KIND_GROUPS[0]!.key);
  const [submitting, setSubmitting] = useState(false);

  const components = useApiQuery<StrategyComponentRow[]>({
    queryKey: ["strategies", "components"],
    path: "/strategies/components",
    select: (raw): StrategyComponentRow[] => {
      // Backend may return either {components: [...]} or a plain array.
      if (Array.isArray(raw)) return raw as StrategyComponentRow[];
      const obj = raw as Partial<ComponentsResponse> | undefined;
      return Array.isArray(obj?.components) ? obj.components : [];
    },
    staleTime: 60_000,
  });

  const grouped = useMemo(() => {
    const map: Record<string, StrategyComponentRow[]> = {};
    for (const row of components.data ?? []) {
      const key = row.kind || "other";
      (map[key] ??= []).push(row);
    }
    return map;
  }, [components.data]);

  const onYamlChange = (next: string) => {
    setYaml(next);
    setSelection({ composerYaml: next });
  };

  const insertStub = (row: StrategyComponentRow) => {
    const stub = `\n  ${row.kind}:\n    class: ${row.name}\n    module_path: ${row.module_path}\n    kwargs: {}\n`;
    onYamlChange(yaml + stub);
    toast.success(`Inserted ${row.name} (${row.kind})`);
  };

  const saveToLibrary = async () => {
    if (!strategyName.trim()) {
      toast.warning("Enter a strategy name");
      return;
    }
    // Parse YAML client-side just to extract class/module_path/kwargs;
    // we rely on a tiny ad-hoc parser for the top-level keys to avoid
    // shipping js-yaml. The backend always re-validates.
    const lines = yaml.split(/\r?\n/);
    let cls = "";
    let modulePath = "";
    for (const line of lines) {
      const mClass = /^class:\s*([\w.]+)\s*$/.exec(line);
      if (mClass) cls = mClass[1]!;
      const mModule = /^module_path:\s*([\w./]+)\s*$/.exec(line);
      if (mModule) modulePath = mModule[1]!;
    }
    if (!cls || !modulePath) {
      toast.error("YAML must declare top-level `class` and `module_path`");
      return;
    }
    setSubmitting(true);
    try {
      const body = {
        name: strategyName.trim(),
        class: cls,
        module_path: modulePath,
        kwargs: { yaml },
        tags: tagInput
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      };
      const res = await apiFetch<{ id: string }>("/strategies", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setSelection({ strategyId: res.id });
      toast.success(`Saved strategy ${strategyName} (${res.id.slice(0, 8)}…)`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-[280px_1fr] gap-3">
      <Card className="flex h-full min-h-0 flex-col">
        <CardHeader>
          <CardTitle>
            <div className="flex items-center gap-2">
              <Library className="h-4 w-4" />
              Component palette
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col p-0">
          <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-0 flex-col">
            <TabsList className="mx-2 mt-2 grid grid-cols-3 gap-1">
              {KIND_GROUPS.slice(0, 3).map((g) => (
                <TabsTrigger key={g.key} value={g.key} className="text-[10px]">
                  {g.label}
                </TabsTrigger>
              ))}
            </TabsList>
            <TabsList className="mx-2 mt-1 grid grid-cols-3 gap-1">
              {KIND_GROUPS.slice(3).map((g) => (
                <TabsTrigger key={g.key} value={g.key} className="text-[10px]">
                  {g.label}
                </TabsTrigger>
              ))}
            </TabsList>
            {KIND_GROUPS.map((g) => (
              <TabsContent key={g.key} value={g.key} className="flex min-h-0 flex-1 flex-col">
                <ScrollArea className="flex-1">
                  <ul className="flex flex-col gap-1 p-2">
                    {(grouped[g.key] ?? []).length === 0 ? (
                      <li className="rounded-md bg-[var(--bg-app)] px-2 py-3 text-center text-[10px] text-[var(--text-secondary)]">
                        {components.isLoading ? "Loading…" : "No components."}
                      </li>
                    ) : null}
                    {(grouped[g.key] ?? []).map((row) => (
                      <li
                        key={`${row.kind}:${row.name}`}
                        className="group flex items-start justify-between gap-2 rounded-md border border-[var(--border-default)] p-2 text-[11px]"
                      >
                        <div className="flex min-w-0 flex-col">
                          <span className="truncate font-medium">{row.name}</span>
                          <span className="truncate text-[10px] font-mono text-[var(--text-secondary)]">
                            {row.module_path}
                          </span>
                          {row.tags?.length ? (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {row.tags.slice(0, 3).map((t) => (
                                <Badge key={t} variant="outline" className="text-[9px]">
                                  {t}
                                </Badge>
                              ))}
                            </div>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          onClick={() => insertStub(row)}
                          className="rounded p-1 text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]"
                          aria-label={`Insert ${row.name}`}
                        >
                          <Plus className="h-3.5 w-3.5" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </ScrollArea>
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>

      <Card className="flex h-full min-h-0 flex-col">
        <CardHeader>
          <CardTitle>YAML composer</CardTitle>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
            <div className="space-y-1">
              <Label htmlFor="composer-name">Strategy name</Label>
              <Input
                id="composer-name"
                value={strategyName}
                onChange={(e) => setStrategyName(e.target.value)}
                placeholder="momentum-aapl"
              />
            </div>
            <div className="space-y-1 lg:col-span-2">
              <Label htmlFor="composer-tags">Tags (comma-separated)</Label>
              <Input
                id="composer-tags"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                placeholder="research, momentum, daily"
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden rounded-md">
            <CodeEditor language="json" value={yaml} onChange={onYamlChange} />
          </div>
          <div className="flex gap-2">
            <Button onClick={saveToLibrary} disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save to library
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate("/strategy-development/simulation")}
              disabled={!selection.composerYaml}
            >
              <PlayCircle className="h-4 w-4" />
              Run simulation
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
