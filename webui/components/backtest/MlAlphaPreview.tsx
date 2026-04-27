"use client";

import { ThunderboltOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, Space, Spin, Table, Tag } from "antd";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";

interface PreviewSignal {
  vt_symbol: string;
  direction: string;
  strength: number;
  confidence: number;
  timestamp: string;
  rationale: string;
}

interface PreviewResponse {
  deployment_id?: string;
  n_signals: number;
  signals: PreviewSignal[];
  error?: string;
  start?: string;
  end?: string;
  n_symbols?: number;
  n_bars?: number;
}

export interface MlAlphaPreviewProps {
  deploymentId: string;
  symbols: string[];
  start: string;
  end: string;
}

export function MlAlphaPreview({ deploymentId, symbols, start, end }: MlAlphaPreviewProps) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await apiFetch<PreviewResponse>(
        `/ml/deployments/${encodeURIComponent(deploymentId)}/preview`,
        {
          method: "POST",
          body: JSON.stringify({ symbols, start, end, last_n: 20 }),
        },
      );
      setData(res);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card
      size="small"
      title="ML alpha preview"
      extra={
        <Button
          size="small"
          type="primary"
          icon={<ThunderboltOutlined />}
          onClick={run}
          loading={loading}
        >
          Preview signals
        </Button>
      }
    >
      {!data && !error && !loading ? (
        <Alert
          type="info"
          showIcon
          message="Run a quick preview to see what predictions this deployment would emit on the chosen universe + window."
        />
      ) : null}
      {loading ? <Spin /> : null}
      {error ? <Alert type="error" showIcon message={error} /> : null}
      {data?.error ? <Alert type="warning" showIcon message={data.error} /> : null}
      {data && !data.error ? (
        <Space direction="vertical" style={{ width: "100%" }} size="small">
          <Descriptions column={3} size="small">
            <Descriptions.Item label="Total signals">{data.n_signals}</Descriptions.Item>
            <Descriptions.Item label="Symbols probed">{data.n_symbols ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="Bars">{data.n_bars ?? "—"}</Descriptions.Item>
            <Descriptions.Item label="Window" span={3}>
              {data.start ?? "—"} → {data.end ?? "—"}
            </Descriptions.Item>
          </Descriptions>
          <Table<PreviewSignal>
            size="small"
            rowKey={(row) => `${row.vt_symbol}-${row.timestamp}`}
            pagination={false}
            dataSource={data.signals}
            columns={[
              { title: "Symbol", dataIndex: "vt_symbol", key: "vt_symbol" },
              {
                title: "Direction",
                dataIndex: "direction",
                key: "direction",
                render: (v: string) => (
                  <Tag color={v === "long" || v === "LONG" ? "green" : "red"}>{v}</Tag>
                ),
              },
              {
                title: "Strength",
                dataIndex: "strength",
                key: "strength",
                render: (v: number) => v.toFixed(3),
              },
              {
                title: "Confidence",
                dataIndex: "confidence",
                key: "confidence",
                render: (v: number) => v.toFixed(3),
              },
              {
                title: "Rationale",
                dataIndex: "rationale",
                key: "rationale",
                ellipsis: true,
              },
            ]}
          />
        </Space>
      ) : null}
    </Card>
  );
}
