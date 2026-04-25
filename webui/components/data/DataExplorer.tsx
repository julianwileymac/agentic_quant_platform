"use client";

import { CloudDownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Form,
  Input,
  Row,
  Select,
  Space,
  Steps,
  Tag,
  Typography,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";
import { useChatStream } from "@/lib/ws";

const { Text, Paragraph } = Typography;

interface CatalogRow {
  id: string;
  name: string;
  provider: string;
  domain: string;
  frequency?: string | null;
  latest_version?: number | null;
  latest_row_count?: number | null;
  updated_at: string;
}

interface IngestForm {
  symbols: string;
  range: [Dayjs, Dayjs];
  interval: string;
  source: string;
}

export function DataExplorer() {
  const { message } = App.useApp();
  const [form] = Form.useForm<IngestForm>();
  const [step, setStep] = useState(0);
  const [taskId, setTaskId] = useState<string | null>(null);
  const stream = useChatStream(taskId);

  const catalog = useApiQuery<CatalogRow[]>({
    queryKey: ["data", "catalog"],
    path: "/data/catalog",
    select: (raw) => (Array.isArray(raw) ? (raw as CatalogRow[]) : []),
  });

  async function submit() {
    const values = await form.validateFields();
    const payload = {
      symbols: values.symbols
        .split(/[,\s]+/)
        .map((s) => s.trim())
        .filter(Boolean),
      start: values.range[0].format("YYYY-MM-DD"),
      end: values.range[1].format("YYYY-MM-DD"),
      interval: values.interval,
      source: values.source,
    };
    if (payload.symbols.length === 0) {
      message.warning("Add at least one symbol");
      return;
    }
    try {
      const res = await apiFetch<{ task_id: string }>("/data/ingest", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setTaskId(res.task_id);
      setStep(2);
      message.success(`Ingest queued: ${res.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Data Explorer"
      subtitle="Ingest market history into the local lake and inspect what is on disk."
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => catalog.refetch()}>
          Refresh
        </Button>
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="Ingest wizard" size="small">
            <Steps
              current={step}
              size="small"
              items={[
                { title: "Universe" },
                { title: "Range" },
                { title: "Stream" },
              ]}
              style={{ marginBottom: 16 }}
            />
            <Form<IngestForm>
              form={form}
              layout="vertical"
              initialValues={{
                symbols: "SPY, AAPL, MSFT",
                interval: "1d",
                source: "yahoo",
                range: [dayjs().subtract(2, "year"), dayjs()],
              }}
              onValuesChange={() => setStep((s) => Math.max(s, 1))}
            >
              <Form.Item
                label="Symbols"
                name="symbols"
                rules={[{ required: true, message: "Required" }]}
              >
                <Input.TextArea autoSize placeholder="SPY, AAPL, MSFT" />
              </Form.Item>
              <Form.Item
                label="Range"
                name="range"
                rules={[{ required: true, message: "Required" }]}
              >
                <DatePicker.RangePicker style={{ width: "100%" }} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="Interval" name="interval">
                    <Select
                      options={[
                        { value: "1d", label: "Daily" },
                        { value: "1h", label: "Hourly" },
                        { value: "5m", label: "5-minute" },
                        { value: "1m", label: "1-minute" },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Source" name="source">
                    <Select
                      options={[
                        { value: "yahoo", label: "yfinance" },
                        { value: "alpaca", label: "Alpaca" },
                        { value: "ibkr", label: "IBKR" },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" icon={<CloudDownloadOutlined />} onClick={submit}>
                Queue ingest
              </Button>
            </Form>
          </Card>
          {taskId ? (
            <Card title="Stream" size="small" style={{ marginTop: 16 }}>
              <Paragraph copyable={{ text: taskId }}>Task: {taskId}</Paragraph>
              <Text type="secondary">Status: {stream.status}</Text>
              <pre
                style={{
                  marginTop: 8,
                  fontSize: 11,
                  maxHeight: 220,
                  overflow: "auto",
                  background: "var(--ant-color-bg-elevated)",
                  padding: 8,
                  borderRadius: 6,
                }}
              >
                {stream.events.map((e, i) => `[${i}] ${JSON.stringify(e)}`).join("\n") || "—"}
              </pre>
            </Card>
          ) : null}
        </Col>
        <Col xs={24} lg={14}>
          <Card title="Catalog" size="small">
            {(catalog.data ?? []).length === 0 ? (
              <Text type="secondary">No datasets indexed yet.</Text>
            ) : (
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                {(catalog.data ?? []).slice(0, 12).map((row) => (
                  <Descriptions
                    key={row.id}
                    size="small"
                    bordered
                    column={4}
                    items={[
                      {
                        key: "name",
                        label: "Name",
                        children: (
                          <Space>
                            <Text strong>{row.name}</Text>
                            <Tag>{row.provider}</Tag>
                            <Tag color="blue">{row.domain}</Tag>
                          </Space>
                        ),
                        span: 4,
                      },
                      { key: "v", label: "Latest", children: `v${row.latest_version ?? "?"}` },
                      { key: "rows", label: "Rows", children: row.latest_row_count ?? "—" },
                      { key: "freq", label: "Frequency", children: row.frequency ?? "—" },
                      { key: "ts", label: "Updated", children: row.updated_at },
                    ]}
                  />
                ))}
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
