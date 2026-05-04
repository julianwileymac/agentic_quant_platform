"use client";

import { BarChartOutlined, DeleteOutlined, ReloadOutlined, SyncOutlined } from "@ant-design/icons";
import { App, Button, Card, Col, Descriptions, Row, Space, Tag, Typography } from "antd";

import { BokehExplorer } from "@/components/visualizations/BokehExplorer";
import { SupersetEmbed } from "@/components/visualizations/SupersetEmbed";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Paragraph, Text } = Typography;

interface VisualizationConfig {
  superset_url: string;
  trino_uri: string;
  trino_catalog: string;
  trino_schema: string;
  trino_http_url?: string | null;
  default_dashboard_uuid?: string | null;
  cache_ttl_seconds: number;
}

interface TrinoHealthPayload {
  ok: boolean;
  coordinator_url?: string | null;
  error?: string | null;
  node_id?: string | null;
  node_version?: string | null;
}

interface SupersetAssetPlan {
  datasets?: { identifier: string; label: string; tags?: string[] }[];
  charts?: { slice_name: string; viz_type: string }[];
}

export function VisualizationsPage() {
  const { message } = App.useApp();
  const config = useApiQuery<VisualizationConfig>({
    queryKey: ["visualizations", "config"],
    path: "/visualizations/config",
  });
  const assets = useApiQuery<SupersetAssetPlan>({
    queryKey: ["visualizations", "superset-assets"],
    path: "/visualizations/superset/assets",
  });
  const trinoHealth = useApiQuery<TrinoHealthPayload>({
    queryKey: ["visualizations", "trino-health"],
    path: "/visualizations/trino/health",
    staleTime: 15_000,
  });

  async function syncSuperset() {
    const response = await apiFetch<{ task_id: string }>("/visualizations/superset/sync", {
      method: "POST",
    });
    message.success(`Superset sync queued: ${response.task_id}`);
  }

  async function clearCache() {
    const response = await apiFetch<{ file: number; redis: number }>(
      "/visualizations/cache/clear",
      { method: "POST", body: JSON.stringify({}) },
    );
    message.success(`Cleared ${response.file} file + ${response.redis} Redis entries`);
  }

  async function syncDataHub() {
    const response = await apiFetch<{ task_id: string }>("/visualizations/datahub/sync", {
      method: "POST",
    });
    message.success(`DataHub Superset push queued: ${response.task_id}`);
  }

  const dashboardUuid = config.data?.default_dashboard_uuid || null;

  return (
    <PageContainer
      title="Visualization Layer"
      subtitle="Trino-backed Superset exploration plus Bokeh charts for agent-produced visuals."
      extra={
        <Space>
          <Button icon={<DeleteOutlined />} onClick={clearCache}>
            Clear cache
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => assets.refetch()}>
            Refresh plan
          </Button>
          <Button icon={<SyncOutlined />} onClick={syncDataHub}>
            Push to DataHub
          </Button>
          <Button type="primary" icon={<SyncOutlined />} onClick={syncSuperset}>
            Sync Superset
          </Button>
        </Space>
      }
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={8}>
          <Card title="BI Stack" loading={config.isLoading}>
            <Descriptions
              column={1}
              size="small"
              items={[
                { key: "superset", label: "Superset", children: <code>{config.data?.superset_url}</code> },
                { key: "trino", label: "Trino", children: <code>{config.data?.trino_uri}</code> },
                ...(config.data?.trino_http_url
                  ? [
                      {
                        key: "trino-http",
                        label: "Trino HTTP (probe)",
                        children: <code>{config.data.trino_http_url}</code>,
                      },
                    ]
                  : []),
                {
                  key: "trino-reach",
                  label: "Trino coordinator",
                  children: (
                    <Space wrap>
                      <Tag color={trinoHealth.data?.ok ? "success" : "error"}>
                        {trinoHealth.isLoading ? "checking" : trinoHealth.data?.ok ? "reachable" : "unreachable"}
                      </Tag>
                      {trinoHealth.data?.node_version ? (
                        <Text type="secondary">{String(trinoHealth.data.node_version)}</Text>
                      ) : null}
                      {trinoHealth.data?.error ? (
                        <Text type="danger" style={{ fontSize: 12 }}>
                          {trinoHealth.data.error}
                        </Text>
                      ) : null}
                    </Space>
                  ),
                },
                {
                  key: "catalog",
                  label: "Catalog",
                  children: `${config.data?.trino_catalog ?? "iceberg"}.${config.data?.trino_schema ?? "aqp"}`,
                },
                {
                  key: "cache",
                  label: "AQP cache TTL",
                  children: `${config.data?.cache_ttl_seconds ?? 0}s`,
                },
              ]}
            />
            <Paragraph style={{ marginTop: 12 }}>
              Use the sync action to provision Superset assets from the AQP dataset presets
              and the live Iceberg catalog rows.
            </Paragraph>
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="Planned Superset Assets" loading={assets.isLoading}>
            <Space direction="vertical" style={{ width: "100%" }}>
              {(assets.data?.datasets ?? []).map((dataset) => (
                <Space key={dataset.identifier} wrap>
                  <BarChartOutlined />
                  <Text strong>{dataset.label}</Text>
                  <Text type="secondary">{dataset.identifier}</Text>
                  {(dataset.tags ?? []).map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                </Space>
              ))}
              {(assets.data?.datasets ?? []).length === 0 ? (
                <Text type="secondary">No matching common datasets are present in Iceberg yet.</Text>
              ) : null}
            </Space>
          </Card>
        </Col>
        <Col xs={24}>
          <SupersetEmbed dashboardUuid={dashboardUuid} />
        </Col>
        <Col xs={24}>
          <BokehExplorer />
        </Col>
      </Row>
    </PageContainer>
  );
}
