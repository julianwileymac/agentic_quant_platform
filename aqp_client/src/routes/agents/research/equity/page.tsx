import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export function ResearchEquityAgentRoute() {
  return (
    <AgentTeamConsole
      specName="research.equity_analyst"
      title="Equity Research Agent"
      description="Equity research analyst. Produces a structured report with thesis, valuation, catalysts, and sensitivity for a given vt_symbol."
    />
  );
}
