import { RegistryBrowser } from "@/components/common/RegistryBrowser";

export function MlZooPage() {
  return (
    <RegistryBrowser
      kind="model"
      title="ML Model Zoo"
      subtitle="Registered ML model classes from `aqp/ml/models/` plus inspiration-rehydrated extractions. Each row is instantiable via {class, module_path, kwargs}."
    />
  );
}
