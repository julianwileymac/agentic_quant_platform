import { RlBuilder } from "@/components/rl/RlBuilder";

/**
 * Phase D — Advantage estimator builder. Reuses the generic
 * `RlBuilder` with `kind="rl_advantage_estimator"` so the Phase 2
 * estimators (ReinforcePlusPlus / GRPO / GAE) get the same pick +
 * configure + save UX as agents / observations / rewards.
 */
export function RlAdvantageBuilderRoute() {
  return (
    <RlBuilder
      kind="rl_advantage_estimator"
      title="Advantage Estimator Builder"
      subtitle="Pick a registered BaseAdvantageEstimator subclass (ReinforcePlusPlus / GRPO / GAE). Saves a `{class, module_path, kwargs}` build-spec that drops into RLExperimentSpec.training.advantage."
      saveEndpoint="/rl/specs/advantage"
    />
  );
}
