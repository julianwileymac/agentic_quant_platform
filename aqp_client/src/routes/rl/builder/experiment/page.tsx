import { RlBuilder } from "@/components/rl/RlBuilder";

export function RlExperimentBuilderRoute() {
  return (
    <RlBuilder
      kind="rl_experiment"
      title="RL Experiment Builder"
      subtitle="Build a hash-locked RLExperimentSpec from a registered experiment class."
      saveEndpoint="/rl/specs/experiment"
    />
  );
}
