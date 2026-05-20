import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export function SelectionAgentRoute() {
  return (
    <AgentTeamConsole
      specName="selection.stock_selector"
      title="Selection Agent"
      description="Stock selection agent. Picks a final tradable universe from the broader equity panel using model scores, risk constraints, and analyst conviction."
    />
  );
}
