import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export function ResearchUniverseAgentRoute() {
  return (
    <AgentTeamConsole
      specName="research.universe_selector"
      title="Universe Selector Agent"
      description="Builds an initial trading universe by filtering on liquidity, market cap, sector exposure, and event-driven catalysts."
    />
  );
}
