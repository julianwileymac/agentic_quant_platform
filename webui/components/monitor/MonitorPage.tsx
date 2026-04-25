"use client";

import { ExportOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Space } from "antd";

import { PageContainer } from "@/components/shell/PageContainer";

const DASH_URL = process.env.NEXT_PUBLIC_DASH_URL ?? "http://localhost:8000/dash/";

export function MonitorPage() {
  return (
    <PageContainer
      title="Strategy Monitor"
      subtitle="Live Plotly/Dash dashboard mounted by the FastAPI backend at /dash."
      extra={
        <Space>
          <Button icon={<ExportOutlined />} href={DASH_URL} target="_blank" rel="noreferrer">
            Open in new tab
          </Button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="Dash iframe (transitional)"
        description="The Strategy Monitor is embedded as an iframe during the Solara → Next migration. The native version replaces this view in a later phase."
      />
      <Card styles={{ body: { padding: 0 } }}>
        <iframe
          src={DASH_URL}
          title="Strategy Monitor"
          style={{
            width: "100%",
            height: "calc(100vh - 280px)",
            border: 0,
            borderRadius: 6,
            background: "#fff",
          }}
        />
      </Card>
    </PageContainer>
  );
}
