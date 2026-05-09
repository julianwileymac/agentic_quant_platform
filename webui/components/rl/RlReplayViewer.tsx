"use client";

import { Card, Slider, Skeleton, Space, Statistic, Typography } from "antd";
import { useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface TrajectoryRow {
  episode: number;
  step: number;
  ts: string | null;
  reward: number;
  info: string;
}

interface EquityRow {
  step: number;
  episode: number;
  portfolio_value: number;
  drawdown: number | null;
  cash: number | null;
}

export function RlReplayViewer({ runId }: { runId: string }) {
  const [episode, setEpisode] = useState<number>(0);
  const [stepIdx, setStepIdx] = useState<number>(0);

  const trajectories = useApiQuery<{ rows: TrajectoryRow[] }>({
    queryKey: ["rl", "run", runId, "trajectories", episode],
    path: `/rl/runs/${runId}/trajectories?episode=${episode}`,
  });
  const equity = useApiQuery<{ rows: EquityRow[] }>({
    queryKey: ["rl", "run", runId, "equity", episode],
    path: `/rl/runs/${runId}/equity?episode=${episode}`,
  });

  const trajRows = trajectories.data?.rows ?? [];
  const equityRows = equity.data?.rows ?? [];

  const currentStep = trajRows[stepIdx];
  const currentEquity = equityRows[stepIdx];

  const totalSteps = useMemo(() => Math.max(trajRows.length, equityRows.length), [trajRows, equityRows]);

  if (trajectories.isLoading || equity.isLoading) {
    return <Skeleton active />;
  }

  return (
    <PageContainer
      title={`Replay run ${runId.slice(0, 12)}…`}
      subtitle="Step-by-step replay of a recorded RL episode."
    >
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space direction="vertical" style={{ width: "100%" }}>
          <Space>
            <Text>Episode</Text>
            <Slider
              value={episode}
              min={0}
              max={Math.max(0, equityRows[equityRows.length - 1]?.episode ?? 0)}
              onChange={setEpisode}
              style={{ width: 240 }}
            />
            <Text>{episode}</Text>
          </Space>
          <Space>
            <Text>Step</Text>
            <Slider
              value={stepIdx}
              min={0}
              max={Math.max(0, totalSteps - 1)}
              onChange={setStepIdx}
              style={{ width: 480 }}
            />
            <Text>
              {stepIdx} / {Math.max(0, totalSteps - 1)}
            </Text>
          </Space>
        </Space>
      </Card>
      <Space size={16} style={{ width: "100%" }} wrap>
        <Card size="small">
          <Statistic
            title="Portfolio value"
            value={currentEquity?.portfolio_value ?? 0}
            precision={2}
          />
        </Card>
        <Card size="small">
          <Statistic title="Drawdown" value={currentEquity?.drawdown ?? 0} precision={4} />
        </Card>
        <Card size="small">
          <Statistic title="Cash" value={currentEquity?.cash ?? 0} precision={0} />
        </Card>
        <Card size="small">
          <Statistic title="Reward" value={currentStep?.reward ?? 0} precision={4} />
        </Card>
      </Space>
      <Card size="small" style={{ marginTop: 12 }} title={`Step ${currentStep?.step ?? "—"}`}>
        <Text>timestamp: {currentStep?.ts ?? "—"}</Text>
        <pre style={{ fontSize: 11, maxHeight: 240, overflow: "auto", marginTop: 8 }}>
          {currentStep?.info ?? ""}
        </pre>
      </Card>
    </PageContainer>
  );
}
