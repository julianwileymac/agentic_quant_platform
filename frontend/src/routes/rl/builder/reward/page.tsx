import { RlBuilder } from "@/components/rl/RlBuilder";

export function RlRewardBuilderRoute() {
  return (
    <RlBuilder
      kind="rl_reward"
      title="RL Reward Builder"
      subtitle="Build a CompositeReward from registered RewardTerm classes."
      saveEndpoint="/rl/specs/reward"
    />
  );
}
