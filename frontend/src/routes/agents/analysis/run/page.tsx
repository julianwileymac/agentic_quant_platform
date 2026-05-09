import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export function AnalysisRunAgentRoute() {
  return (
    <AgentTeamConsole
      specName="analysis.run_critic"
      title="Run Analyst"
      description="Reviews an entire AgentRun trace end-to-end: cost, tool ROI, hallucination risk, and unfinished sub-tasks. Outputs a structured run-level evaluation."
    />
  );
}
