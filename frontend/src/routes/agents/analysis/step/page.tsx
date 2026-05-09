import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export function AnalysisStepAgentRoute() {
  return (
    <AgentTeamConsole
      specName="analysis.step_critic"
      title="Step Analyst"
      description="Audits a single agent step (or LLM call) for tool-use correctness, factual grounding, and rationale quality. Produces a critique payload usable by the orchestrator."
    />
  );
}
