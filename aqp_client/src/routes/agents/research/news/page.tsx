import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export function ResearchNewsAgentRoute() {
  return (
    <AgentTeamConsole
      specName="research.news_miner"
      title="News Miner Agent"
      description="News miner. Surfaces material events, regulatory filings, and sentiment shifts across the requested universe."
    />
  );
}
