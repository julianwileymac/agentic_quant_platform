import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export function AnalysisPortfolioAgentRoute() {
  return (
    <AgentTeamConsole
      specName="analysis.portfolio_critic"
      title="Portfolio Analyst"
      description="Surfaces aggregate portfolio risks: concentration, factor tilts, gap-risk, drawdown profile. Produces a structured advisory payload for the trader/PM agents."
    />
  );
}
