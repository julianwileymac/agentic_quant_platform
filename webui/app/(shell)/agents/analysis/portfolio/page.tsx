import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export const metadata = { title: "Portfolio Analyst | AQP" };

export default function Page() {
  return (
    <AgentTeamConsole
      specName="analysis.portfolio"
      title="Portfolio Analyst"
      description="Interpret portfolio aggregate performance and surface regulatory exposure."
      defaultPrompt="Summarise current portfolio risk concentrations and any regulatory exposure flags."
    />
  );
}
