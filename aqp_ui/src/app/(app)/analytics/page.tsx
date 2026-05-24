import { Card } from "antd";

export const dynamic = "force-dynamic";

export default function AnalyticsPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
          Analytics
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--text-secondary)" }}>
          Portfolio tearsheets, rolling Sharpe, underwater curves, QuantStats.
        </p>
      </header>
      <Card>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          Tearsheet renders enqueue through{" "}
          <code>POST /analytics/portfolio/tearsheet</code> and stream progress
          via the canonical task WebSocket.
        </p>
      </Card>
    </div>
  );
}
