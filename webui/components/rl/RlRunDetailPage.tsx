"use client";

import { Card, Col, Descriptions, Row, Skeleton, Statistic, Tag } from "antd";
import Link from "next/link";
import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";

interface RunPayload {
  id: string;
  target: string;
  status: string;
  mlflow_run_id: string | null;
  checkpoint: string | null;
  mean_reward: number | null;
  sharpe: number | null;
  max_drawdown: number | null;
  final_value: number | null;
  total_return: number | null;
  result_summary: Record<string, unknown>;
  started_at: string | null;
  ended_at: string | null;
}

interface EquityRow {
  step: number;
  episode: number;
  portfolio_value: number;
  drawdown: number | null;
}

interface RewardDecompRow {
  step: number;
  episode: number;
  term_name: string;
  contribution: number;
}

interface EpisodeRow {
  id: string;
  episode: number;
  mean_reward: number;
  portfolio_value: number | null;
  length: number | null;
  created_at: string | null;
}

const COLORS = ["#3b82f6", "#22c55e", "#ef4444", "#f59e0b", "#a855f7", "#14b8a6", "#0ea5e9"];

export function RlRunDetailPage({ runId }: { runId: string }) {
  const run = useApiQuery<RunPayload>({
    queryKey: ["rl", "run", runId],
    path: `/rl/runs/${runId}`,
    refetchInterval: 5_000,
  });
  const equity = useApiQuery<{ rows: EquityRow[] }>({
    queryKey: ["rl", "run", runId, "equity"],
    path: `/rl/runs/${runId}/equity`,
    refetchInterval: 10_000,
  });
  const rewardDecomp = useApiQuery<{ rows: RewardDecompRow[] }>({
    queryKey: ["rl", "run", runId, "reward-decomposition"],
    path: `/rl/runs/${runId}/reward-decomposition`,
    refetchInterval: 10_000,
  });
  const episodes = useApiQuery<{ episodes: EpisodeRow[] }>({
    queryKey: ["rl", "run", runId, "episodes"],
    path: `/rl/runs/${runId}/episodes`,
    refetchInterval: 10_000,
  });

  const equityChart = useMemo(() => {
    return (equity.data?.rows ?? []).map((r) => ({
      step: r.step,
      episode: r.episode,
      portfolio_value: r.portfolio_value,
      drawdown: r.drawdown ?? 0,
    }));
  }, [equity.data]);

  const decompChart = useMemo(() => {
    const rows = rewardDecomp.data?.rows ?? [];
    if (!rows.length) return { rows: [], terms: [] };
    const byStep: Record<number, Record<string, number>> = {};
    const terms = new Set<string>();
    for (const row of rows) {
      const bucket = byStep[row.step] ?? { step: row.step };
      bucket[row.term_name] = row.contribution;
      byStep[row.step] = bucket;
      terms.add(row.term_name);
    }
    return {
      rows: Object.values(byStep).sort((a, b) => (a.step ?? 0) - (b.step ?? 0)),
      terms: Array.from(terms),
    };
  }, [rewardDecomp.data]);

  if (run.isLoading || !run.data) return <Skeleton active />;

  return (
    <PageContainer
      title={`RL run ${runId.slice(0, 12)}…`}
      subtitle={`Target ${run.data.target} — ${run.data.status}`}
      extra={
        <Link href={`/rl/runs/${runId}/replay`}>
          <Tag color="blue">Replay</Tag>
        </Link>
      }
    >
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Mean reward" value={run.data.mean_reward ?? 0} precision={4} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Sharpe" value={run.data.sharpe ?? 0} precision={3} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Max drawdown" value={run.data.max_drawdown ?? 0} precision={3} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small">
            <Statistic title="Total return" value={(run.data.total_return ?? 0) * 100} suffix="%" precision={2} />
          </Card>
        </Col>
      </Row>
      <Card size="small" title="Equity curve" style={{ marginBottom: 16 }}>
        <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={equityChart}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="step" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="portfolio_value" stroke="#22c55e" dot={false} />
              <Line type="monotone" dataKey="drawdown" stroke="#ef4444" dot={false} yAxisId={0} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card size="small" title="Reward decomposition" style={{ marginBottom: 16 }}>
        {decompChart.rows.length === 0 ? (
          <em>No decomposition rows yet.</em>
        ) : (
          <div style={{ height: 320 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={decompChart.rows}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="step" />
                <YAxis />
                <Tooltip />
                <Legend />
                {decompChart.terms.map((term, i) => (
                  <Line
                    key={term}
                    type="monotone"
                    dataKey={term}
                    stroke={COLORS[i % COLORS.length]}
                    dot={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
      <Row gutter={16}>
        <Col xs={24} md={14}>
          <Card size="small" title="Run metadata">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="MLflow run">{run.data.mlflow_run_id ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Checkpoint">{run.data.checkpoint ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Started">{run.data.started_at ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Ended">{run.data.ended_at ?? "—"}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card size="small" title="Episodes">
            {episodes.data?.episodes?.length ? (
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12 }}>
                {episodes.data.episodes.map((ep) => (
                  <li key={ep.id}>
                    ep {ep.episode}: r̄ = {ep.mean_reward.toFixed(4)}, pv ={" "}
                    {ep.portfolio_value?.toFixed(0) ?? "—"}, len = {ep.length ?? "—"}
                  </li>
                ))}
              </ul>
            ) : (
              <em>No episode rows yet.</em>
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
