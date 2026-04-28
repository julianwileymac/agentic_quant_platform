import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export const metadata = { title: "News Miner | AQP" };

export default function Page() {
  return (
    <AgentTeamConsole
      specName="research.news_miner"
      title="News Miner"
      description="Mines recent news and regulatory flags for a symbol or topic."
      defaultPrompt="Surface news + sentiment + regulatory flags affecting AAPL.NASDAQ over the last 7 days."
    />
  );
}
