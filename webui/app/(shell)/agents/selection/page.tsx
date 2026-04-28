import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export const metadata = { title: "Stock Selector | AQP" };

export default function Page() {
  return (
    <AgentTeamConsole
      specName="selection.stock_selector"
      title="Stock Selector"
      description="Picks the top-N tickers for a (model, strategy, universe, agent) quadruple. Persists each pick + rationale to agent_annotations for downstream optimisation."
      defaultPrompt="Given the universe and the chosen (model, strategy), pick the top 10 names with the highest expected risk-adjusted returns over the next 20 trading days. Veto names with active FDA recalls."
    />
  );
}
