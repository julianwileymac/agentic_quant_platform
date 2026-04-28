import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export const metadata = { title: "Run Analyst | AQP" };

export default function Page() {
  return (
    <AgentTeamConsole
      specName="analysis.run"
      title="Run Analyst"
      description="Interpret a backtest / paper / live run end-to-end."
      defaultPrompt="Interpret the most recent backtest run for the momentum strategy."
    />
  );
}
