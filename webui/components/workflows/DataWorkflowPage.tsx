"use client";

import { App } from "antd";

import { PageContainer } from "@/components/shell/PageContainer";
import { DATA_PALETTE } from "@/components/flow/palettes";
import { WorkflowEditor } from "@/components/flow/WorkflowEditor";
import { serializeDataPipeline } from "@/components/flow/serializers";
import type { FlowGraph } from "@/components/flow/types";
import { apiFetch } from "@/lib/api/client";

const ACCENTS: Record<string, string> = {
  Source: "#10b981",
  Transform: "#3b82f6",
  Feature: "#a855f7",
  Parquet: "#f59e0b",
  Index: "#f59e0b",
  Live: "#ef4444",
};

const STARTER_GRAPH: FlowGraph = {
  domain: "data",
  version: 1,
  nodes: [
    {
      id: "src-1",
      type: "aqp",
      position: { x: 80, y: 60 },
      data: {
        kind: "Source",
        label: "yfinance",
        params: { provider: "yahoo", symbols: ["SPY", "AAPL"], interval: "1d" },
      },
    },
    {
      id: "tx-1",
      type: "aqp",
      position: { x: 360, y: 60 },
      data: { kind: "Transform", label: "Adjust", params: { kind: "adjust" } },
    },
    {
      id: "snk-1",
      type: "aqp",
      position: { x: 640, y: 60 },
      data: { kind: "Parquet", label: "Lake parquet", params: { path: "data/parquet/" } },
    },
  ],
  edges: [
    { id: "e1", source: "src-1", target: "tx-1" },
    { id: "e2", source: "tx-1", target: "snk-1" },
  ],
};

export function DataWorkflowPage() {
  const { message } = App.useApp();

  async function run(graph: FlowGraph) {
    const payload = serializeDataPipeline(graph);
    const sourceJobs = payload.jobs.filter((j) => j.kind === "Source");
    if (sourceJobs.length === 0) {
      message.warning("Add at least one Source node");
      return;
    }
    let queued = 0;
    const errors: string[] = [];
    for (const job of sourceJobs) {
      const symbols = (job.params.symbols as string[]) ?? [];
      try {
        await apiFetch("/data/ingest", {
          method: "POST",
          body: JSON.stringify({
            symbols,
            start: job.params.start ?? "2022-01-01",
            end: job.params.end ?? "2024-12-31",
            interval: job.params.interval ?? "1d",
            source: job.params.provider ?? "yahoo",
          }),
        });
        queued += 1;
      } catch (err) {
        errors.push((err as Error).message);
      }
    }
    if (errors.length) {
      message.error(`Queued ${queued}/${sourceJobs.length}: ${errors.join("; ")}`);
    } else {
      message.success(`Queued ${queued} ingest job(s).`);
    }
  }

  return (
    <PageContainer
      title="Data pipeline editor"
      subtitle="Visually wire sources → transforms → features → sinks."
      full
    >
      <div style={{ flex: 1, padding: "0 16px 16px" }}>
        <WorkflowEditor
          domain="data"
          paletteSections={DATA_PALETTE}
          initialGraph={STARTER_GRAPH}
          accentByKind={ACCENTS}
          onRun={run}
        />
      </div>
    </PageContainer>
  );
}
