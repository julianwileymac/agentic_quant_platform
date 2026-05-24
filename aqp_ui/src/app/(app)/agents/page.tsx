import { Card } from "antd";

export const dynamic = "force-dynamic";

export default function AgentsPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Agents
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Hash-locked agent specs. Every run is immutable and replayable.
        </p>
      </header>
      <Card>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Agents run through <code>AgentRuntime</code> with cost caps and
          guardrails. The trace view here surfaces telemetry from
          <code>agent_runs_v2</code> and the LangGraph decision log.
        </p>
      </Card>
    </div>
  );
}
