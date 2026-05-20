import { apiFetch } from "./client";

export interface IndicatorSpec {
  name: string;
  category: string;
  description?: string;
  formula?: string;
  inputs: string[];
  output?: string;
  default_kwargs?: Record<string, unknown>;
  tags?: string[];
}

export const indicatorsApi = {
  list: (): Promise<IndicatorSpec[]> => apiFetch<IndicatorSpec[]>("/data/indicators"),
  get: (name: string): Promise<IndicatorSpec> =>
    apiFetch<IndicatorSpec>(`/data/indicators/${encodeURIComponent(name)}`),
};
