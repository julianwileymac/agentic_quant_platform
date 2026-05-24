import { Card } from "antd";

export const dynamic = "force-dynamic";

export default function PortfolioPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Portfolio
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Live positions, target weights, and risk overlays across active runs.
        </p>
      </header>
      <Card>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          The FinRL-X four-stage weight-centric pipeline (<code>f_S</code> →
          <code>f_A</code> → <code>f_T</code> → <code>f_R</code>) drives both
          paper and live execution.
        </p>
      </Card>
    </div>
  );
}
