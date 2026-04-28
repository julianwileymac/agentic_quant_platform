import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export const metadata = { title: "Step Analyst | AQP" };

export default function Page() {
  return (
    <AgentTeamConsole
      specName="analysis.step"
      title="Step Analyst"
      description="Interpret a single agent step's tool calls + outputs."
      defaultPrompt="Inspect step #3 from agent run abc-123 and verdict it."
    />
  );
}
