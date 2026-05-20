import type { PaletteSection } from "@/components/flow/types";

/**
 * Drag tiles for the Agent Crew Editor — composes a CrewAI-style
 * spec (LLM + Memory + Tools + Agents + Tasks). The serializer maps
 * each kind to a slot in the resulting payload.
 */
export const AGENT_CREW_PALETTE: PaletteSection[] = [
  {
    title: "LLM",
    items: [
      {
        kind: "LLM",
        label: "Quick model",
        description: "Fast, low-cost completions",
        accent: "#10b981",
        defaultParams: { tier: "quick", temperature: 0.4 },
      },
      {
        kind: "LLM",
        label: "Deep model",
        description: "Reasoning-heavy completions",
        accent: "#10b981",
        defaultParams: { tier: "deep", temperature: 0.2 },
      },
    ],
  },
  {
    title: "Memory",
    items: [
      {
        kind: "Memory",
        label: "Conversation memory",
        accent: "#a855f7",
        defaultParams: { kind: "conversation" },
      },
      {
        kind: "Memory",
        label: "Vector memory (Chroma)",
        accent: "#a855f7",
        defaultParams: { kind: "vector", store: "chroma" },
      },
    ],
  },
  {
    title: "Tools",
    items: [
      {
        kind: "Tool",
        label: "Backtest tool",
        description: "POST /backtest/run",
        accent: "#3b82f6",
        defaultParams: { tool: "backtest_run" },
      },
      {
        kind: "Tool",
        label: "Data lookup",
        description: "GET /data/{vt_symbol}/bars",
        accent: "#3b82f6",
        defaultParams: { tool: "data_lookup" },
      },
      {
        kind: "Tool",
        label: "Web search",
        accent: "#3b82f6",
        defaultParams: { tool: "web_search" },
      },
    ],
  },
  {
    title: "Agents",
    items: [
      { kind: "Agent", label: "Researcher", accent: "#f59e0b", defaultParams: { role: "researcher" } },
      { kind: "Agent", label: "Analyst", accent: "#f59e0b", defaultParams: { role: "analyst" } },
      { kind: "Agent", label: "Trader", accent: "#f59e0b", defaultParams: { role: "trader" } },
    ],
  },
  {
    title: "Tasks",
    items: [
      { kind: "Task", label: "Task", accent: "#8b5cf6", defaultParams: { description: "" } },
      { kind: "Output", label: "Output", accent: "#ef4444", defaultParams: {} },
    ],
  },
];

export const AGENT_CREW_NODE_ACCENTS: Record<string, string> = {
  LLM: "#10b981",
  Memory: "#a855f7",
  Tool: "#3b82f6",
  Agent: "#f59e0b",
  Task: "#8b5cf6",
  Output: "#ef4444",
};
