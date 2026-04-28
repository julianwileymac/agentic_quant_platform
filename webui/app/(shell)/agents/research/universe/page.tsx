import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export const metadata = { title: "Universe Selector | AQP" };

export default function Page() {
  return (
    <AgentTeamConsole
      specName="research.universe"
      title="Universe Selector"
      description="Interactive universe shaping with RAG-justified picks and exclusions."
      defaultPrompt="Build a 30-name universe of US large-cap technology and healthcare names with adequate liquidity. Flag names with notable regulatory exposure."
    />
  );
}
