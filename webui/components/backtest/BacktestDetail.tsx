"use client";

import { ArrowLeftOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Descriptions, Row, Space, Tabs, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { EquityChart } from "@/components/charts";
import { BacktestTimelineChart } from "@/components/backtest/BacktestTimelineChart";
import { InterruptPanel } from "@/components/backtest/InterruptPanel";
import { JudgeReport } from "@/components/backtest/JudgeReport";
import { ReplayDrawer } from "@/components/backtest/ReplayDrawer";
import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import { usePageContextStore } from "@/lib/store/page-context";

interface FindingEdit {
  decision_id: string;
  vt_symbol?: string;
  ts?: string;
  action?: "BUY" | "SELL" | "HOLD" | string;
  size_pct?: number;
  rationale?: string;
}

interface RunDetail {
  id: string;
  status: string;
  start?: string | null;
  end?: string | null;
  sharpe?: number | null;
  sortino?: number | null;
  max_drawdown?: number | null;
  total_return?: number | null;
  final_equity?: number | null;
  dataset_hash?: string | null;
  created_at?: string;
}

interface PlotResponse {
  data?: Array<{ x?: string[]; y?: number[]; name?: string; type?: string }>;
}

const { Text } = Typography;

function plotToEquity(plot: PlotResponse | undefined): Array<{ timestamp: string; value: number }> {
  const trace = plot?.data?.find((t) => Array.isArray(t.x) && Array.isArray(t.y));
  if (!trace || !trace.x || !trace.y) return [];
  const xs = trace.x;
  const ys = trace.y;
  const n = Math.min(xs.length, ys.length);
  const out: Array<{ timestamp: string; value: number }> = [];
  for (let i = 0; i < n; i += 1) {
    out.push({ timestamp: xs[i] ?? String(i), value: Number(ys[i]) });
  }
  return out;
}

export function BacktestDetail({ backtestId }: { backtestId: string }) {
  const router = useRouter();
  const setContext = usePageContextStore((s) => s.setContext);
  const [replayEdits, setReplayEdits] = useState<FindingEdit[]>([]);
  const [replayJudgeId, setReplayJudgeId] = useState<string | null>(null);
  const [replayOpen, setReplayOpen] = useState(false);

  useEffect(() => {
    setContext({ page: "/backtest", backtest_id: backtestId });
    return () => setContext({ backtest_id: undefined });
  }, [backtestId, setContext]);

  const detail = useApiQuery<RunDetail>({
    queryKey: ["backtest", "run", backtestId],
    path: `/backtest/runs/${backtestId}`,
    refetchInterval: (query) => {
      const status = (query.state.data as RunDetail | undefined)?.status;
      return status === "running" || status === "queued" ? 4000 : false;
    },
  });

  const equityPlot = useApiQuery<PlotResponse>({
    queryKey: ["backtest", "plot", backtestId, "equity"],
    path: `/backtest/runs/${backtestId}/plot/equity`,
  });
  const drawdownPlot = useApiQuery<PlotResponse>({
    queryKey: ["backtest", "plot", backtestId, "drawdown"],
    path: `/backtest/runs/${backtestId}/plot/drawdown`,
  });

  const equity = plotToEquity(equityPlot.data);
  const drawdown = plotToEquity(drawdownPlot.data);

  const status = detail.data?.status;
  const statusColor =
    status === "completed" ? "green" : status === "failed" ? "red" : status === "running" ? "blue" : "default";

  return (
    <PageContainer
      title={
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => router.push("/backtest")} />
          Backtest run
          <Text type="secondary" copyable={{ text: backtestId }} style={{ fontSize: 12 }}>
            {backtestId}
          </Text>
          {status ? <Tag color={statusColor}>{status}</Tag> : null}
        </Space>
      }
    >
      {detail.error ? <Alert type="error" message={detail.error.message} /> : null}
      <Row gutter={16}>
        <Col xs={24} lg={16}>
          <Card title="Equity curve" size="small">
            {equity.length ? (
              <EquityChart data={equity} height={320} />
            ) : (
              <Text type="secondary">Equity curve unavailable.</Text>
            )}
          </Card>
          <Card title="Drawdown" size="small" style={{ marginTop: 16 }}>
            {drawdown.length ? (
              <EquityChart data={drawdown} height={220} />
            ) : (
              <Text type="secondary">Drawdown unavailable.</Text>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="Summary" size="small">
            <Descriptions
              column={1}
              size="small"
              items={[
                { key: "status", label: "Status", children: <Tag color={statusColor}>{status ?? "—"}</Tag> },
                { key: "start", label: "Start", children: detail.data?.start ?? "—" },
                { key: "end", label: "End", children: detail.data?.end ?? "—" },
                {
                  key: "sharpe",
                  label: "Sharpe",
                  children: detail.data?.sharpe?.toFixed?.(3) ?? "—",
                },
                {
                  key: "sortino",
                  label: "Sortino",
                  children: detail.data?.sortino?.toFixed?.(3) ?? "—",
                },
                {
                  key: "dd",
                  label: "Max drawdown",
                  children:
                    detail.data?.max_drawdown !== null && detail.data?.max_drawdown !== undefined
                      ? `${(detail.data.max_drawdown * 100).toFixed(2)}%`
                      : "—",
                },
                {
                  key: "ret",
                  label: "Total return",
                  children:
                    detail.data?.total_return !== null && detail.data?.total_return !== undefined
                      ? `${(detail.data.total_return * 100).toFixed(2)}%`
                      : "—",
                },
                {
                  key: "eq",
                  label: "Final equity",
                  children: detail.data?.final_equity?.toLocaleString?.() ?? "—",
                },
                { key: "ds", label: "Dataset hash", children: detail.data?.dataset_hash ?? "—" },
              ]}
            />
          </Card>
        </Col>
      </Row>
      {status === "running" || status === "queued" ? (
        <div style={{ marginTop: 16 }}>
          <InterruptPanel backtestId={backtestId} />
        </div>
      ) : null}
      <Tabs
        style={{ marginTop: 16 }}
        items={[
          {
            key: "decisions",
            label: "Decisions",
            children: (
              <Card size="small">
                <BacktestTimelineChart backtestId={backtestId} />
              </Card>
            ),
          },
          {
            key: "judge",
            label: "Judge",
            children: (
              <JudgeReport
                backtestId={backtestId}
                onApplyFinding={(finding, judgeReportId) => {
                  setReplayEdits([
                    {
                      decision_id: String(finding.decision_id ?? ""),
                      vt_symbol: finding.vt_symbol,
                      ts: finding.ts,
                      action: finding.recommended_action,
                      size_pct: finding.recommended_size_pct,
                      rationale: finding.rationale,
                    },
                  ]);
                  setReplayJudgeId(judgeReportId);
                  setReplayOpen(true);
                }}
              />
            ),
          },
          {
            key: "raw",
            label: "Raw plot JSON",
            children: (
              <Card size="small">
                <pre
                  style={{
                    fontSize: 11,
                    maxHeight: 320,
                    overflow: "auto",
                    background: "var(--ant-color-bg-elevated)",
                    padding: 12,
                    borderRadius: 6,
                  }}
                >
                  {JSON.stringify(equityPlot.data ?? {}, null, 2)}
                </pre>
              </Card>
            ),
          },
        ]}
      />
      <ReplayDrawer
        backtestId={backtestId}
        open={replayOpen}
        initialEdits={replayEdits}
        judgeReportId={replayJudgeId}
        onClose={() => setReplayOpen(false)}
        onQueued={() => {
          setReplayEdits([]);
        }}
      />
    </PageContainer>
  );
}
