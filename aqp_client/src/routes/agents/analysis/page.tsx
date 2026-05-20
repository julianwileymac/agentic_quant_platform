import { Activity, BarChart3, Layers } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";
import { PageContainer } from "@/components/shell/PageContainer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TILES = [
  {
    href: "/agents/analysis/step",
    title: "Step Analyst",
    description: "Audit a single agent step for tool-use correctness and rationale quality.",
    icon: Layers,
  },
  {
    href: "/agents/analysis/run",
    title: "Run Analyst",
    description: "Review a full AgentRun: cost, tool ROI, hallucination risk, unfinished sub-tasks.",
    icon: Activity,
  },
  {
    href: "/agents/analysis/portfolio",
    title: "Portfolio Analyst",
    description: "Aggregate portfolio risks: concentration, factor tilts, gap-risk, drawdown.",
    icon: BarChart3,
  },
];

export function AnalysisAgentsHubRoute() {
  // ``?spec=<name>`` deep-links from the Agent Templates Gallery render
  // the AgentTeamConsole inline against the requested spec; otherwise
  // we fall back to the curated tile overview.
  const [searchParams] = useSearchParams();
  const spec = searchParams.get("spec");
  if (spec && spec.trim()) {
    return (
      <AgentTeamConsole
        specName={spec.trim()}
        title="Analysis Agent"
        description="Critic / analyst spec dispatched from the Agent Templates Gallery."
      />
    );
  }
  return (
    <PageContainer
      title="Analysis Agents"
      subtitle="Critic / analyst spec-driven agents. Score steps, runs, and portfolios in a structured advisory format."
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {TILES.map((tile) => {
          const Icon = tile.icon;
          return (
            <Link key={tile.href} to={tile.href} className="block">
              <Card className="h-full transition-colors hover:border-[var(--info-fg)]">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Icon className="h-4 w-4" />
                    {tile.title}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-[var(--text-secondary)]">{tile.description}</p>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </PageContainer>
  );
}
