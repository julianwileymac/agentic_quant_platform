import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export function TraderAgentRoute() {
  return (
    <AgentTeamConsole
      specName="trader.signal_emitter"
      title="Trader Agent"
      description="Trader agent. Translates portfolio constraints + alpha signals into BUY/SELL/HOLD orders with sizing recommendations."
    />
  );
}
