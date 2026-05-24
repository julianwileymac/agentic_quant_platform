"use client";

import { Card, Empty } from "antd";

export default function BacktestsPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
        Backtests
      </h1>
      <Card>
        <Empty
          description={
            <span style={{ color: "var(--text-secondary)" }}>
              Backtest history will appear here. Run a strategy from{" "}
              <a href="/strategies" style={{ color: "var(--accent-primary)" }}>
                Strategies
              </a>{" "}
              to populate this list.
            </span>
          }
        />
      </Card>
    </div>
  );
}
