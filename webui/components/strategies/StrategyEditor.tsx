"use client";

import { ArrowLeftOutlined, PlayCircleOutlined, SaveOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Row,
  Skeleton,
  Space,
  Tabs,
  Tag,
  Typography,
} from "antd";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery, useApiMutation } from "@/lib/api/hooks";
import { usePageContextStore } from "@/lib/store/page-context";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
  loading: () => <Skeleton active />,
});

const { Text } = Typography;

interface StrategyDetail {
  id: string;
  name: string;
  status: string;
  version: number;
  author: string;
  config_yaml: string;
  versions: Array<{ id: string; version: number; author: string; created_at: string; notes?: string | null }>;
  tests: Array<{
    id: string;
    status: string;
    engine?: string | null;
    sharpe?: number | null;
    total_return?: number | null;
    max_drawdown?: number | null;
    backtest_id?: string | null;
    created_at: string;
  }>;
}

interface StrategyEditorProps {
  mode: "create" | "edit";
  strategyId?: string;
}

const DEFAULT_YAML = `# AQP strategy YAML
strategy:
  name: my_strategy
  asset_class: equity
  symbols: [SPY, AAPL, MSFT]
  signals:
    - kind: sma_cross
      fast: 10
      slow: 30
  sizing:
    kind: equal_weight
  risk:
    max_position_pct: 0.1
`;

export function StrategyEditor({ mode, strategyId }: StrategyEditorProps) {
  const router = useRouter();
  const setContext = usePageContextStore((s) => s.setContext);
  const { message } = App.useApp();
  const [name, setName] = useState("");
  const [yaml, setYaml] = useState<string>(mode === "create" ? DEFAULT_YAML : "");

  const detail = useApiQuery<StrategyDetail>({
    queryKey: ["strategies", "detail", strategyId ?? ""],
    path: strategyId ? `/strategies/${strategyId}` : "/strategies/",
    enabled: mode === "edit" && Boolean(strategyId),
  });

  useEffect(() => {
    if (mode === "edit" && detail.data) {
      setName(detail.data.name);
      setYaml(detail.data.config_yaml ?? "");
      setContext({ page: "/strategies", strategy_id: detail.data.id });
    }
    return () => {
      setContext({ strategy_id: undefined });
    };
  }, [mode, detail.data, setContext]);

  const create = useApiMutation<{ name: string; config_yaml: string }, StrategyDetail>({
    path: "/strategies/",
    method: "POST",
    toBody: (vars) => ({ ...vars, author: "webui" }),
    onSuccess: (data) => {
      message.success("Strategy created");
      router.push(`/strategies/${data.id}`);
    },
    onError: (err) => message.error(err.message),
  });

  const update = useApiMutation<{ id: string; config_yaml: string }, StrategyDetail>({
    path: (vars) => `/strategies/${vars.id}`,
    method: "PUT",
    toBody: (vars) => ({ config_yaml: vars.config_yaml, author: "webui" }),
    onSuccess: () => {
      message.success("Strategy updated");
      detail.refetch();
    },
    onError: (err) => message.error(err.message),
  });

  async function runTest() {
    if (!strategyId) return;
    try {
      const res = await apiFetch<{ task_id: string }>(`/strategies/${strategyId}/test`, {
        method: "POST",
        body: JSON.stringify({ engine: "EventDrivenBacktester" }),
      });
      message.success(`Backtest queued (task ${res.task_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  function save() {
    if (!yaml.trim()) {
      message.warning("Strategy YAML is empty");
      return;
    }
    if (mode === "create") {
      if (!name.trim()) {
        message.warning("Name is required");
        return;
      }
      create.mutate({ name, config_yaml: yaml });
    } else if (strategyId) {
      update.mutate({ id: strategyId, config_yaml: yaml });
    }
  }

  return (
    <PageContainer
      title={
        <Space>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => router.push("/strategies")}
          />
          {mode === "create"
            ? "New strategy"
            : (detail.data?.name ?? <Skeleton.Input size="small" active />)}
          {detail.data ? <Tag color="blue">v{detail.data.version}</Tag> : null}
        </Space>
      }
      subtitle={mode === "create" ? "Author a new versioned strategy" : "Edit, version, and test"}
      extra={
        <Space>
          {mode === "edit" ? (
            <Button icon={<PlayCircleOutlined />} onClick={runTest}>
              Run backtest
            </Button>
          ) : null}
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={save}
            loading={create.isPending || update.isPending}
          >
            {mode === "create" ? "Create" : "Save version"}
          </Button>
        </Space>
      }
    >
      <Tabs
        defaultActiveKey="yaml"
        items={[
          {
            key: "yaml",
            label: "YAML",
            children: (
              <Row gutter={16}>
                <Col xs={24} lg={mode === "create" ? 8 : 24}>
                  {mode === "create" ? (
                    <Card title="Metadata" size="small">
                      <Form layout="vertical">
                        <Form.Item label="Name" required>
                          <Input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. mean_reversion_v1"
                          />
                        </Form.Item>
                      </Form>
                    </Card>
                  ) : null}
                </Col>
                <Col xs={24} lg={mode === "create" ? 16 : 24}>
                  <Card size="small">
                    <div style={{ height: 480 }}>
                      <MonacoEditor
                        height="100%"
                        defaultLanguage="yaml"
                        value={yaml}
                        onChange={(v) => setYaml(v ?? "")}
                        theme="vs-dark"
                        options={{
                          fontSize: 13,
                          minimap: { enabled: false },
                          scrollBeyondLastLine: false,
                        }}
                      />
                    </div>
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: "versions",
            label: "Versions",
            disabled: mode === "create",
            children: (
              <Card>
                {detail.data?.versions?.length ? (
                  <Descriptions
                    column={1}
                    items={detail.data.versions.map((v) => ({
                      key: v.id,
                      label: (
                        <Space>
                          <Tag>v{v.version}</Tag>
                          <Text type="secondary">{v.created_at}</Text>
                        </Space>
                      ),
                      children: (
                        <Space size={8} wrap>
                          <Text>{v.author}</Text>
                          {v.notes ? <Text type="secondary">{v.notes}</Text> : null}
                        </Space>
                      ),
                    }))}
                  />
                ) : (
                  <Text type="secondary">No prior versions yet.</Text>
                )}
              </Card>
            ),
          },
          {
            key: "tests",
            label: "Tests",
            disabled: mode === "create",
            children: (
              <Card>
                {detail.data?.tests?.length ? (
                  detail.data.tests.map((t) => (
                    <div key={t.id} style={{ marginBottom: 8 }}>
                      <Space>
                        <Tag color={t.status === "completed" ? "green" : "blue"}>{t.status}</Tag>
                        <Text>{t.engine ?? "—"}</Text>
                        <Text type="secondary">Sharpe</Text>
                        <Text strong>{t.sharpe ?? "—"}</Text>
                        <Text type="secondary">Return</Text>
                        <Text strong>
                          {t.total_return !== null && t.total_return !== undefined
                            ? `${(t.total_return * 100).toFixed(2)}%`
                            : "—"}
                        </Text>
                        {t.backtest_id ? (
                          <Button
                            type="link"
                            size="small"
                            onClick={() => router.push(`/backtest/${t.backtest_id}`)}
                          >
                            Open run
                          </Button>
                        ) : null}
                      </Space>
                    </div>
                  ))
                ) : (
                  <Text type="secondary">No tests recorded yet.</Text>
                )}
              </Card>
            ),
          },
        ]}
      />
    </PageContainer>
  );
}
