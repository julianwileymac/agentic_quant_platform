import { useState } from "react";

import { RegistryBrowser } from "@/components/common/RegistryBrowser";
import { PageContainer } from "@/components/shell/PageContainer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const KINDS = [
  { value: "rl_env", label: "Environments" },
  { value: "rl_observation", label: "Observations" },
  { value: "rl_action", label: "Actions" },
  { value: "rl_reward", label: "Rewards" },
  { value: "rl_termination", label: "Terminations" },
  { value: "rl_policy", label: "Policies" },
  // Phase 3 of hybrid agentic-RL rollout: Transformer / RNN /
  // Autoencoder / PatchTST backbones register under this kind.
  { value: "rl_policy_backbone", label: "Policy backbones" },
  // Phase 2 of hybrid agentic-RL rollout: ReinforcePlusPlus / GRPO /
  // GAE advantage estimators register under this kind.
  { value: "rl_advantage_estimator", label: "Advantage estimators" },
  { value: "rl_data", label: "Data pipelines" },
  { value: "rl_ensembler", label: "Ensemblers" },
  { value: "rl_experiment", label: "Experiments" },
  { value: "rl_trajectory_store", label: "Trajectory stores" },
];

export function RlComponentLibrary() {
  const [tab, setTab] = useState("rl_env");
  return (
    <PageContainer
      title="RL Component Library"
      subtitle="Every concrete RL component registered through the RLComponent metaclass. Pivot by kind, search by alias / class / docstring."
    >
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="flex flex-wrap">
          {KINDS.map((k) => (
            <TabsTrigger key={k.value} value={k.value}>
              {k.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {KINDS.map((k) => (
          <TabsContent key={k.value} value={k.value} className="mt-3">
            <RegistryBrowser
              kind={k.value}
              title={k.label}
              subtitle={`Components registered as kind=${k.value}.`}
            />
          </TabsContent>
        ))}
      </Tabs>
    </PageContainer>
  );
}
