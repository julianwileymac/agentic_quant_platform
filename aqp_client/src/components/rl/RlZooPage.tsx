import { RegistryBrowser } from "@/components/common/RegistryBrowser";

export function RlZooPage() {
  return (
    <RegistryBrowser
      kind="rl_agent"
      title="RL Agent Zoo"
      subtitle="Registered RL agents from SB3 / sb3-contrib / ElegantRL / RLlib / CleanRL adapters plus the LLM-hybrid agent."
    />
  );
}
