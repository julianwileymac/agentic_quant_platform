import type { FlowSchema } from "@/lib/analysis/api";
import type { PaletteItem, PaletteSection } from "@/components/flow/types";

export const NAMESPACE_ACCENTS: Record<string, string> = {
  profiling: "#0ea5e9",
  distribution: "#06b6d4",
  outlier: "#f59e0b",
  imputation: "#84cc16",
  regression: "#a855f7",
  time_series: "#22c55e",
  derivatives: "#ec4899",
  portfolio: "#3b82f6",
  factors: "#8b5cf6",
  microstructure: "#ef4444",
};

export const NAMESPACE_TITLES: Record<string, string> = {
  profiling: "Profiling",
  distribution: "Distribution",
  outlier: "Outliers",
  imputation: "Imputation",
  regression: "Regression",
  time_series: "Time Series",
  derivatives: "Derivatives",
  portfolio: "Portfolio",
  factors: "Factors",
  microstructure: "Microstructure",
};

/**
 * Build palette sections from the flow catalog. The Composer canvas
 * uses these to spawn nodes whose ``kind`` is the namespaced flow
 * name (e.g. ``distribution.shapiro_wilk``).
 */
export function buildAnalysisPalette(flows: FlowSchema[]): PaletteSection[] {
  const grouped: Record<string, PaletteItem[]> = {};
  for (const flow of flows) {
    const ns = flow.namespace || "other";
    const accent = NAMESPACE_ACCENTS[ns] ?? "#64748b";
    if (!grouped[ns]) grouped[ns] = [];
    grouped[ns].push({
      kind: flow.name,
      label: flow.label,
      description: flow.description,
      accent,
      defaultParams: extractDefaults(flow.params_schema),
    });
  }
  const sections: PaletteSection[] = [];
  for (const ns of Object.keys(NAMESPACE_TITLES)) {
    if (!grouped[ns]?.length) continue;
    sections.push({
      title: NAMESPACE_TITLES[ns]!,
      items: grouped[ns]!.sort((a, b) => a.label.localeCompare(b.label)),
    });
  }
  // Catch-all for unknown namespaces.
  for (const [ns, items] of Object.entries(grouped)) {
    if (NAMESPACE_TITLES[ns]) continue;
    sections.push({ title: ns, items });
  }
  return sections;
}

export function buildAccentMap(flows: FlowSchema[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const flow of flows) {
    out[flow.name] = NAMESPACE_ACCENTS[flow.namespace] ?? "#64748b";
  }
  return out;
}

function extractDefaults(schema: Record<string, unknown>): Record<string, unknown> {
  const properties =
    (schema.properties as Record<string, Record<string, unknown>> | undefined) ?? {};
  const out: Record<string, unknown> = {};
  for (const [name, raw] of Object.entries(properties)) {
    if (raw.default !== undefined) out[name] = raw.default;
  }
  return out;
}
