"use client";

import { ExperimentOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  App,
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Row,
  Select,
  Skeleton,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

const { Text, Title, Paragraph } = Typography;

interface EquitySection {
  section_key?: string;
  ticker?: string;
  text?: string;
  highlights?: string[];
}

interface EquityReportSummary {
  id: string;
  vt_symbol: string;
  as_of: string;
  peers: string[];
  cost_usd: number;
  status: string;
  error?: string | null;
  created_at: string;
}

interface EquityReportDetail extends EquityReportSummary {
  sections: Record<string, EquitySection>;
  usage: Record<string, unknown>;
  valuation: Record<string, unknown>;
  sensitivity: { cells?: Array<{ growth: number; discount: number; value: number | null }> };
  catalysts: Array<{ kind: string; headline: string; summary: string; ts?: string | null }>;
}

interface SubmitResp {
  task_id: string;
  stream_url?: string;
}

const SECTION_TITLES: Record<string, string> = {
  tagline: "Tagline",
  company_overview: "Company Overview",
  investment_overview: "Investment Overview",
  valuation_overview: "Valuation Overview",
  risks: "Risks",
  competitor_analysis: "Competitor Analysis",
  news_summary: "News Summary",
  major_takeaways: "Major Takeaways",
};

const SECTION_ORDER = [
  "tagline",
  "major_takeaways",
  "company_overview",
  "investment_overview",
  "valuation_overview",
  "competitor_analysis",
  "risks",
  "news_summary",
];

export function EquityReportPage({ vtSymbol }: { vtSymbol?: string }) {
  const { message } = App.useApp();
  const [symbolInput, setSymbolInput] = useState<string>(vtSymbol ?? "AAPL");
  const [peerInput, setPeerInput] = useState<string[]>(["MSFT", "GOOGL"]);
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);

  const reports = useApiQuery<EquityReportSummary[]>({
    queryKey: ["equity-reports", symbolInput],
    path: "/agents/equity-reports",
    query: { vt_symbol: symbolInput, limit: 25 },
    refetchInterval: stream.status === "open" ? 3000 : false,
  });

  const detail = useApiQuery<EquityReportDetail>({
    queryKey: ["equity-report", selectedReportId ?? "_"],
    path: selectedReportId
      ? `/agents/equity-report/${encodeURIComponent(selectedReportId)}`
      : "/agents/equity-report/_",
    enabled: Boolean(selectedReportId),
  });

  async function submit() {
    try {
      const res = await apiFetch<SubmitResp>("/agents/equity-report", {
        method: "POST",
        body: JSON.stringify({
          vt_symbol: symbolInput,
          as_of: new Date().toISOString(),
          peers: peerInput,
        }),
      });
      setTaskId(res.task_id);
      message.success(`Equity report queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  const sectionEntries = detail.data
    ? SECTION_ORDER
        .map((k) => [k, detail.data!.sections[k]] as const)
        .filter(([, v]) => Boolean(v))
    : [];

  return (
    <PageContainer
      title={
        <Space>
          <ExperimentOutlined />
          Equity Research Report
        </Space>
      }
      subtitle="FinRobot-style section-by-section research with valuation + catalysts."
      extra={
        <Button
          type="primary"
          icon={<ExperimentOutlined />}
          onClick={submit}
        >
          Run report
        </Button>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="Run" size="small">
            <Form layout="vertical">
              <Form.Item label="Ticker">
                <Input value={symbolInput} onChange={(e) => setSymbolInput(e.target.value)} />
              </Form.Item>
              <Form.Item label="Peers">
                <Select
                  mode="tags"
                  tokenSeparators={[",", " "]}
                  value={peerInput}
                  onChange={(v) => setPeerInput(v as string[])}
                />
              </Form.Item>
            </Form>
            {taskId ? (
              <Alert
                type={stream.error ? "error" : "info"}
                message={`Task ${taskId} (${stream.status})`}
                description={stream.error || stream.events.slice(-1)[0]?.message || ""}
                showIcon
              />
            ) : null}
          </Card>
          <Card
            size="small"
            title="History"
            style={{ marginTop: 16 }}
            extra={
              <Button
                size="small"
                icon={<ReloadOutlined />}
                onClick={() => reports.refetch()}
              />
            }
          >
            <List
              size="small"
              dataSource={reports.data ?? []}
              locale={{ emptyText: "No reports yet" }}
              renderItem={(r) => (
                <List.Item
                  actions={[
                    <Button
                      key="view"
                      size="small"
                      type="link"
                      onClick={() => setSelectedReportId(r.id)}
                    >
                      View
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Text strong>{r.vt_symbol}</Text>
                        <Tag>{r.as_of?.slice(0, 10)}</Tag>
                        <Tag color="blue">${r.cost_usd?.toFixed?.(3) ?? "0.000"}</Tag>
                      </Space>
                    }
                    description={r.created_at?.slice(0, 19)}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          {!selectedReportId ? (
            <Card>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="Pick a report on the left or run a new one."
              />
            </Card>
          ) : detail.isLoading || !detail.data ? (
            <Skeleton active />
          ) : (
            <>
              <Card size="small" title={`${detail.data.vt_symbol} — ${detail.data.as_of?.slice(0, 10)}`}>
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="Status">
                    <Tag color={detail.data.status === "completed" ? "green" : "default"}>
                      {detail.data.status}
                    </Tag>
                  </Descriptions.Item>
                  <Descriptions.Item label="Cost">
                    ${detail.data.cost_usd.toFixed(4)}
                  </Descriptions.Item>
                  <Descriptions.Item label="Peers" span={2}>
                    <Space wrap>
                      {detail.data.peers.map((p) => (
                        <Tag key={p}>{p}</Tag>
                      ))}
                    </Space>
                  </Descriptions.Item>
                </Descriptions>
              </Card>
              <Card size="small" title="Sections" style={{ marginTop: 16 }}>
                {sectionEntries.length === 0 ? (
                  <Empty />
                ) : (
                  <Tabs
                    items={sectionEntries.map(([key, section]) => ({
                      key,
                      label: SECTION_TITLES[key] ?? key,
                      children: (
                        <div>
                          {section?.text ? (
                            <Paragraph style={{ whiteSpace: "pre-wrap" }}>
                              {section.text}
                            </Paragraph>
                          ) : null}
                          {section?.highlights?.length ? (
                            <List
                              size="small"
                              header={<Text strong>Highlights</Text>}
                              dataSource={section.highlights}
                              renderItem={(h) => <List.Item>{h}</List.Item>}
                            />
                          ) : null}
                        </div>
                      ),
                    }))}
                  />
                )}
              </Card>
              <Card size="small" title="Catalysts" style={{ marginTop: 16 }}>
                {!detail.data.catalysts?.length ? (
                  <Empty />
                ) : (
                  <List
                    size="small"
                    dataSource={detail.data.catalysts}
                    renderItem={(c) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <Space>
                              <Tag color="cyan">{c.kind}</Tag>
                              <Text strong>{c.headline}</Text>
                              {c.ts ? <Text type="secondary">{c.ts.slice(0, 10)}</Text> : null}
                            </Space>
                          }
                          description={c.summary}
                        />
                      </List.Item>
                    )}
                  />
                )}
              </Card>
              <Card size="small" title="Valuation sensitivity" style={{ marginTop: 16 }}>
                {!detail.data.sensitivity?.cells?.length ? (
                  <Empty />
                ) : (
                  <Table
                    size="small"
                    rowKey={(r) => `${r.growth}-${r.discount}`}
                    dataSource={detail.data.sensitivity.cells}
                    pagination={false}
                    columns={[
                      {
                        title: "Growth",
                        dataIndex: "growth",
                        render: (v: number) => `${(v * 100).toFixed(1)}%`,
                        width: 100,
                      },
                      {
                        title: "Discount",
                        dataIndex: "discount",
                        render: (v: number) => `${(v * 100).toFixed(1)}%`,
                        width: 100,
                      },
                      {
                        title: "Value",
                        dataIndex: "value",
                        render: (v: number | null) =>
                          v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 2 }),
                      },
                    ]}
                  />
                )}
              </Card>
            </>
          )}
        </Col>
      </Row>
    </PageContainer>
  );
}
