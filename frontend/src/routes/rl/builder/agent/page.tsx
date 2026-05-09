import { RlBuilder } from "@/components/rl/RlBuilder";

export function RlAgentBuilderRoute() {
  return (
    <RlBuilder
      kind="rl_agent"
      title="RL Agent Builder"
      subtitle="Pick a registered RL agent class and persist a configured `{class, module_path, kwargs}` build-spec."
      saveEndpoint="/rl/specs/agent"
    />
  );
}
