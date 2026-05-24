import { Card } from "antd";

export const dynamic = "force-dynamic";

export default function WorkflowsPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Workflows
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Seven adapter kinds: graph / crew / debate / fusion / execution /
          schedule / studio.
        </p>
      </header>
      <Card>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Composed through <code>WorkflowSpec</code> + <code>WorkflowRuntime</code>.
          Halt-all fans out from the top-bar kill switch.
        </p>
      </Card>
    </div>
  );
}
