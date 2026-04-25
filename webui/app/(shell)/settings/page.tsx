"use client";

import { Button, Card, Col, Descriptions, Row, Space, Switch, Typography } from "antd";

import { PageContainer } from "@/components/shell/PageContainer";
import { useUiStore } from "@/lib/store/ui";

const { Text } = Typography;

export default function SettingsPage() {
  const themeMode = useUiStore((s) => s.themeMode);
  const toggleTheme = useUiStore((s) => s.toggleTheme);

  return (
    <PageContainer title="Settings" subtitle="Local UI preferences and runtime endpoints.">
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <Card title="Appearance">
            <Space>
              <Text>Dark mode</Text>
              <Switch checked={themeMode === "dark"} onChange={() => toggleTheme()} />
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="Endpoints">
            <Descriptions
              column={1}
              size="small"
              items={[
                {
                  key: "api",
                  label: "API",
                  children: <code>{process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}</code>,
                },
                {
                  key: "ws",
                  label: "WebSocket",
                  children: <code>{process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000"}</code>,
                },
                {
                  key: "dash",
                  label: "Dash",
                  children: <code>{process.env.NEXT_PUBLIC_DASH_URL ?? "http://localhost:8000/dash/"}</code>,
                },
                {
                  key: "mlflow",
                  label: "MLflow",
                  children: <code>{process.env.NEXT_PUBLIC_MLFLOW_URL ?? "http://localhost:5000"}</code>,
                },
              ]}
            />
            <div style={{ marginTop: 12 }}>
              <Button type="link" href="/docs">
                Open docs
              </Button>
            </div>
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
