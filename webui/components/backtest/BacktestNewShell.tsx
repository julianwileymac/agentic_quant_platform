"use client";

import { Card, Tabs } from "antd";

import { AgentBacktestWizard } from "@/components/backtest/AgentBacktestWizard";
import { BacktestLab } from "@/components/backtest/BacktestLab";

/**
 * Top-level "New backtest" page. Defaults to the registry-driven Agent
 * Backtest wizard; the legacy raw-YAML editor is one tab away for
 * power users.
 */
export function BacktestNewShell() {
  return (
    <Card size="small" style={{ background: "transparent", border: "none" }} bodyStyle={{ padding: 0 }}>
      <Tabs
        defaultActiveKey="wizard"
        items={[
          {
            key: "wizard",
            label: "Agent backtest wizard",
            children: <AgentBacktestWizard />,
          },
          {
            key: "raw",
            label: "Advanced (raw YAML/JSON)",
            children: <BacktestLab />,
          },
        ]}
      />
    </Card>
  );
}
