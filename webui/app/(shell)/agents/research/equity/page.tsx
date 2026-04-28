import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export const metadata = { title: "Equity Researcher | AQP" };

export default function Page() {
  return (
    <AgentTeamConsole
      specName="research.equity"
      title="Equity Researcher"
      description="Long-form equity research synthesis with hierarchical RAG citations."
      defaultPrompt="Produce an equity research note for AAPL.NASDAQ with the standard sections."
    />
  );
}
