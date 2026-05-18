import { apiFetch } from "./client";

export interface ProviderControl {
  provider: string;
  deep_model: string;
  quick_model: string;
  ollama_host: string;
  vllm_base_url: string;
  ollama_online: boolean;
  ollama_models: string[];
  vllm_online: boolean;
  vllm_models: string[];
}

export interface LlmProfile {
  name: string;
  provider: string;
  model: string;
  description?: string;
  enabled: boolean;
}

export const getProviderControl = (): Promise<ProviderControl> =>
  apiFetch<ProviderControl>("/agentic/provider-control");

export const listLlmProfiles = (): Promise<LlmProfile[]> =>
  apiFetch<LlmProfile[]>("/llm/providers");
