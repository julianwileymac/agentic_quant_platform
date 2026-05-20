import { ArrowRight, FlaskConical, GitBranch, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BundledExample } from "@/lib/api/strategyLibrary";

import { useStrategyDev } from "./StrategyDevContext";

interface Props {
  example: BundledExample;
  /** Optional KPI strip — e.g. measured Sharpe / MDD from a RAG hit. */
  kpis?: Array<{ label: string; value: string | number }>;
  /** Surface the source_path under the title. */
  showSourcePath?: boolean;
}

/**
 * Phase B card for the gallery and library tabs. "Use as template"
 * routes to the appropriate studio with the right deep-link query
 * string AND stashes the full payload on `StrategyDevContext.gallerySelection`
 * so the studio can hydrate richer state than what fits in URL params.
 */
export function ExampleCard({ example, kpis = [], showSourcePath = false }: Props) {
  const navigate = useNavigate();
  const { setSelection } = useStrategyDev();

  const handleUseTemplate = () => {
    setSelection({
      gallerySelection: {
        kind: example.kind,
        slug: example.slug,
        payload: example.payload,
      },
    });
    if (example.kind === "alpha_factor") {
      const formula = String(
        (example.payload as Record<string, unknown>).formula ?? "",
      );
      const name = example.name;
      const search = new URLSearchParams({ formula, name });
      navigate(`/strategy-development/alpha-factors?${search.toString()}`);
      return;
    }
    if (example.kind === "rl_spec") {
      const search = new URLSearchParams({ template: example.slug });
      navigate(`/rl/lab?${search.toString()}`);
      return;
    }
    if (example.kind === "agent_spec") {
      navigate(`/agents/quant?template=${encodeURIComponent(example.slug)}`);
      return;
    }
  };

  const icon =
    example.kind === "alpha_factor" ? (
      <Sparkles className="h-4 w-4" />
    ) : example.kind === "rl_spec" ? (
      <FlaskConical className="h-4 w-4" />
    ) : (
      <GitBranch className="h-4 w-4" />
    );

  return (
    <Card>
      <CardHeader className="gap-1">
        <CardTitle className="flex items-center gap-2 text-sm">
          {icon}
          <span className="truncate">{example.name}</span>
          <Badge variant="secondary" className="ml-auto">
            {example.kind.replace("_", " ")}
          </Badge>
        </CardTitle>
        {showSourcePath && example.source_path ? (
          <code className="block truncate text-[10px] text-[var(--text-secondary)]">
            {example.source_path}
          </code>
        ) : null}
      </CardHeader>
      <CardContent className="grid gap-3">
        {example.description ? (
          <p className="text-xs text-[var(--text-secondary)]">{example.description}</p>
        ) : null}
        {kpis.length > 0 ? (
          <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
            {kpis.map((kpi) => (
              <div key={kpi.label} className="rounded bg-[var(--bg-elevated)] p-2">
                <div className="text-[10px] text-[var(--text-secondary)]">{kpi.label}</div>
                <div className="font-mono text-xs">{String(kpi.value)}</div>
              </div>
            ))}
          </div>
        ) : null}
        {example.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {example.tags.slice(0, 6).map((tag) => (
              <Badge key={tag} variant="outline" className="font-mono">
                {tag}
              </Badge>
            ))}
          </div>
        ) : null}
        <Button size="sm" onClick={handleUseTemplate} className="w-fit gap-2">
          Use as template <ArrowRight className="h-3 w-3" />
        </Button>
      </CardContent>
    </Card>
  );
}
