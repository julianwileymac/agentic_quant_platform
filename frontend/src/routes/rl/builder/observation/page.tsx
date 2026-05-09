import { RlBuilder } from "@/components/rl/RlBuilder";

export function RlObservationBuilderRoute() {
  return (
    <RlBuilder
      kind="rl_observation"
      title="RL Observation Builder"
      subtitle="Compose feature blocks (FinRL stockstats / covariance / turbulence / VIX / lookback) into an observation builder."
      saveEndpoint="/rl/specs/observation"
    />
  );
}
