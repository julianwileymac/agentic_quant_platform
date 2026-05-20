import { RlBuilder } from "@/components/rl/RlBuilder";

/**
 * Phase D — Policy backbone builder. Reuses the generic `RlBuilder`
 * with `kind="rl_policy_backbone"` so the Phase 3 backbones
 * (Transformer / Recurrent / Autoencoder / PatchTST) get the same
 * pick + configure + save UX as agents / observations / rewards.
 */
export function RlBackboneBuilderRoute() {
  return (
    <RlBuilder
      kind="rl_policy_backbone"
      title="Policy Backbone Builder"
      subtitle="Pick a registered TimeSeriesEncoder subclass (Transformer / RNN / Autoencoder / PatchTST). Saves a `{class, module_path, kwargs}` build-spec that the SB3 BackboneFeaturesExtractor consumes via the standard `policy_kwargs` payload."
      saveEndpoint="/rl/specs/backbone"
    />
  );
}
