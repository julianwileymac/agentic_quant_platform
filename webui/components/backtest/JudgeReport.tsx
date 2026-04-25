"use client";

import {
  AuditOutlined,
  CheckOutlined,
  EditOutlined,
  StopOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Empty,
  List,
  Progress,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Text, Paragraph, Title } = Typography;

interface Finding {
  decision_id?: string | null;
  vt_symbol?: string;
  ts?: string;
  severity?: "info" | "warn" | "error" | string;
  verdict?: "keep" | "edit" | "veto" | string;
  recommended_action?: "BUY" | "SELL" | "HOLD" | string;
  recommended_size_pct?: number;
  rationale?: string;
}

interface JudgeReportRow {
  id: string;
  backtest_id: string;
  judge_class: string;
  score: number;
  summary?: string | null;
  findings: Finding[];
  cost_usd: number;
  provider?: string | null;
  model?: string | null;
  rubric?: string | null;
  created_at?: string | null;
}

interface JudgeListItem {
  alias: string;
  qualname: string;
  tags: string[];
}

interface SubmitResp {
  task_id: string;
  stream_url?: string;
}

const SEVERITY_COLOR: Record<string, string> = {
  info: "blue",
  warn: "orange",
  error: "red",
};

const VERDICT_COLOR: Record<string, string> = {
  keep: "green",
  edit: "orange",
  veto: "red",
};

const VERDICT_ICON: Record<string, React.ReactNode> = {
  keep: <CheckOutlined />,
  edit: <EditOutlined />,
  veto: <StopOutlined />,
};

export function JudgeReport({
  backtestId,
  onApplyFinding,
}: {
  backtestId: string;
  onApplyFinding?: (finding: Finding, judgeReportId: string) => void;
}) {
  const { message } = App.useApp();
  const [pickedJudge, setPickedJudge] = useState<string>("LLMJudge");
  const [running, setRunning] = useState(false);

  const judges = useApiQuery<{ judges: JudgeListItem[] }>({
    queryKey: ["agentic", "judges"],
    path: "/agentic/judges",
    staleTime: 60_000,
  });

  const reports = useApiQuery<JudgeReportRow[]>({
    queryKey: ["agentic", "judge", backtestId],
    path: `/agentic/judge/${backtestId}`,
    refetchInterval: running ? 4000 : false,
  });

  const latest = (reports.data ?? [])[0];

  async function runJudge() {
    setRunning(true);
    try {
      const judgeAlias = pickedJudge || "LLMJudge";
      await apiFetch<SubmitResp>(`/agentic/judge/${backtestId}`, {
        method: "POST",
        body: JSON.stringify({
          judge: {
            class: judgeAlias,
            module_path: "aqp.backtest.llm_judge",
            kwargs: { tier: "deep", rubric: "default" },
          },
        }),
      });
      message.success("Judge queued");
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      // Stop polling after a short window — user can refetch manually too.
      setTimeout(() => setRunning(false), 60_000);
    }
  }

  return (
    <Card
      size="small"
      title={
        <Space>
          <AuditOutlined />
          LLM-as-judge critique
        </Space>
      }
      extra={
        <Space>
          <Select
            size="small"
            value={pickedJudge}
            onChange={setPickedJudge}
            style={{ width: 180 }}
            options={(judges.data?.judges ?? []).map((j) => ({
              value: j.alias,
              label: j.alias,
            }))}
          />
          <Button type="primary" size="small" onClick={runJudge} loading={running}>
            Run judge
          </Button>
        </Space>
      }
    >
      {!latest ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="No judge report yet — pick a judge and click Run."
        />
      ) : (
        <>
          <Space wrap style={{ marginBottom: 8 }}>
            <Tag color="blue">{latest.judge_class}</Tag>
            {latest.provider ? <Tag>{latest.provider}</Tag> : null}
            {latest.model ? <Tag>{latest.model}</Tag> : null}
            {latest.rubric ? <Tag color="purple">rubric: {latest.rubric}</Tag> : null}
            <Tooltip title="Aggregate score across all decisions">
              <Progress
                percent={Math.round((latest.score ?? 0) * 100)}
                size="small"
                style={{ width: 120 }}
              />
            </Tooltip>
            <Text type="secondary">cost: ${latest.cost_usd?.toFixed?.(4) ?? "0.0000"}</Text>
          </Space>
          {latest.summary ? (
            <Paragraph style={{ marginTop: 8 }}>{latest.summary}</Paragraph>
          ) : null}
          {latest.findings?.some((f) => f.severity === "error") ? (
            <Alert
              type="error"
              showIcon
              icon={<WarningFilled />}
              message={`${latest.findings.filter((f) => f.severity === "error").length} error-severity finding(s)`}
              style={{ marginBottom: 8 }}
            />
          ) : null}
          <Title level={5}>Findings</Title>
          <List
            size="small"
            dataSource={latest.findings ?? []}
            locale={{ emptyText: "No findings emitted." }}
            renderItem={(f) => (
              <List.Item
                actions={
                  onApplyFinding
                    ? [
                        <Button
                          key="apply"
                          size="small"
                          type="link"
                          onClick={() => onApplyFinding(f, latest.id)}
                          disabled={f.verdict === "keep"}
                        >
                          Apply suggestion
                        </Button>,
                      ]
                    : undefined
                }
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Tag color={SEVERITY_COLOR[String(f.severity)] ?? "default"}>
                        {f.severity ?? "info"}
                      </Tag>
                      <Tag color={VERDICT_COLOR[String(f.verdict)] ?? "default"}>
                        {VERDICT_ICON[String(f.verdict)]} {f.verdict ?? "keep"}
                      </Tag>
                      <Text strong>{f.vt_symbol}</Text>
                      <Text type="secondary">{f.ts}</Text>
                      <Tag>{f.recommended_action}</Tag>
                      <Tag color="cyan">size: {(f.recommended_size_pct ?? 0).toFixed(2)}</Tag>
                    </Space>
                  }
                  description={f.rationale}
                />
              </List.Item>
            )}
          />
        </>
      )}
    </Card>
  );
}
