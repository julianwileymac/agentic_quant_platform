import type { Metadata } from "next";

import { ModelsPage } from "@/components/models/ModelsPage";

export const metadata: Metadata = {
  title: "Models & Providers · AQP",
  description: "Manage local LLM models (Ollama pull/delete) and vLLM serving profiles.",
};

export default function ModelsRoute() {
  return <ModelsPage />;
}
