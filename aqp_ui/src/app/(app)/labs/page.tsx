import { Card } from "antd";

export const dynamic = "force-dynamic";

export default function LabsPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Labs
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Jupyter and Dagster sandbox sessions with per-session isolation.
        </p>
      </header>
      <Card>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Each lab gets a unique tempdir, its own Redis namespace under{" "}
          <code>aqp:sandbox:&#123;session_id&#125;:*</code>, and a context-var
          env override so production endpoints are never reached by mistake.
        </p>
      </Card>
    </div>
  );
}
