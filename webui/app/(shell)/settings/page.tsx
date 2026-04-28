"use client";

import {
  Button,
  Card,
  Col,
  Descriptions,
  Row,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
} from "antd";

import { BacktestDataSources } from "@/components/settings/BacktestDataSources";
import { DataFabricCard } from "@/components/settings/DataFabricCard";
import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import { useUiStore } from "@/lib/store/ui";

const { Text } = Typography;

interface ProviderControl {
  provider: string;
  deep_model: string;
  quick_model: string;
  ollama_host: string;
  vllm_base_url: string;
  ollama_online: boolean;
  ollama_models: string[];
  vllm_online: boolean;
  vllm_models: string[];
}

export default function SettingsPage() {
  const themeMode = useUiStore((s) => s.themeMode);
  const toggleTheme = useUiStore((s) => s.toggleTheme);

  const providerControl = useApiQuery<ProviderControl>({
    queryKey: ["agentic", "provider-control"],
    path: "/agentic/provider-control",
    staleTime: 10_000,
  });

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
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <Card
            title="LLM provider control"
            extra={
              providerControl.isLoading ? (
                <Spin size="small" />
              ) : (
                <Tag color={providerControl.data?.provider ? "blue" : "default"}>
                  {providerControl.data?.provider || "unset"}
                </Tag>
              )
            }
          >
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="Active provider">
                {providerControl.data?.provider || <Text type="secondary">unset</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="Deep / Quick">
                <code>{providerControl.data?.deep_model || "—"}</code>
                {" / "}
                <code>{providerControl.data?.quick_model || "—"}</code>
              </Descriptions.Item>
              <Descriptions.Item label="Ollama">
                <Tag color={providerControl.data?.ollama_online ? "green" : "default"}>
                  {providerControl.data?.ollama_online ? "online" : "offline"}
                </Tag>
                <code style={{ marginLeft: 8 }}>
                  {providerControl.data?.ollama_host || "(host unset)"}
                </code>
              </Descriptions.Item>
              <Descriptions.Item label="vLLM">
                <Tag color={providerControl.data?.vllm_online ? "green" : "default"}>
                  {providerControl.data?.vllm_online ? "online" : "offline"}
                </Tag>
                <code style={{ marginLeft: 8 }}>
                  {providerControl.data?.vllm_base_url || "(base url unset)"}
                </code>
              </Descriptions.Item>
            </Descriptions>
            <Space style={{ marginTop: 16 }}>
              <Button type="primary" href="/models">
                Open Models &amp; Providers
              </Button>
              <Button onClick={() => providerControl.refetch()}>Refresh status</Button>
            </Space>
          </Card>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <DataFabricCard />
        </Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24}>
          <BacktestDataSources />
        </Col>
      </Row>
    </PageContainer>
  );
}
