import { Newspaper, Search, Telescope } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";
import { PageContainer } from "@/components/shell/PageContainer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TILES = [
  {
    href: "/agents/research/news",
    title: "News Miner",
    description: "Mine material events, regulatory filings, and sentiment across a universe.",
    icon: Newspaper,
  },
  {
    href: "/agents/research/equity",
    title: "Equity Research",
    description: "Run a structured equity report (thesis / valuation / catalysts / sensitivity).",
    icon: Search,
  },
  {
    href: "/agents/research/universe",
    title: "Universe Selector",
    description: "Build an initial trading universe from liquidity / sector / event filters.",
    icon: Telescope,
  },
];

export function ResearchAgentsHubRoute() {
  // The Agent Templates Gallery deep-links specs into this hub via
  // ``?spec=<name>``. In that case render the AgentTeamConsole pointed
  // at the requested spec; without a query param fall back to the
  // tiles overview that lists the curated leaf consoles.
  const [searchParams] = useSearchParams();
  const spec = searchParams.get("spec");
  if (spec && spec.trim()) {
    return (
      <AgentTeamConsole
        specName={spec.trim()}
        title="Research Agent"
        description="Spec-driven research persona dispatched from the Agent Templates Gallery."
      />
    );
  }
  return (
    <PageContainer
      title="Research Agents"
      subtitle="Spec-driven research personas. Each launches via /agents/runs/v2/sync and writes the populated run to agent_runs_v2."
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
