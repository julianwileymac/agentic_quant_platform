"use client";

import { App, Button, Card, Space, Table, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { apiFetch } from "@/lib/api/client";

const { Paragraph, Text } = Typography;

interface StreamingLink {
  id: string;
  dataset_catalog_id?: string | null;
  dataset_namespace?: string | null;
  dataset_table?: string | null;
  kind: string;
  target_ref: string;
  cluster_ref?: string | null;
  direction: string;
  metadata: Record<string, unknown>;
  enabled: boolean;
}

interface StreamingDatasetLinksProps {
  datasetId: string;
}

export function StreamingDatasetLinks({ datasetId }: StreamingDatasetLinksProps) {
  const { message } = App.useApp();
  const [rows, setRows] = useState<StreamingLink[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  function refresh() {
    setLoading(true);
    apiFetch<StreamingLink[]>(`/datasets/${datasetId}/streaming-links`)
      .then(setRows)
      .catch((err) => message.error((err as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [datasetId]);

  async function discover() {
    setRefreshing(true);
    try {
      await apiFetch("/streaming/links/refresh", { method: "POST" });
      message.success("Discovery queued");
      // Give the task a moment then refresh
      setTimeout(refresh, 1500);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setRefreshing(false);
    }
  }

  async function deleteLink(row: StreamingLink) {
    try {
      await apiFetch(`/datasets/${datasetId}/streaming-links/${row.id}`, {
        method: "DELETE",
      });
      message.success("Link deleted");
      refresh();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <Card
      title="Streaming components"
      extra={
        <Button onClick={discover} loading={refreshing} size="small">
          Discover
        </Button>
      }
    >
      <Paragraph type="secondary">
        Kafka topics, Flink jobs, Airbyte connections, dbt models, Dagster
        assets, and producers linked to this dataset. Refresh runs the
        background task <Text code>refresh_links</Text> which infers links by
        naming conventions.
      </Paragraph>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        size="middle"
        pagination={{ pageSize: 25 }}
        columns={[
          {
            title: "Kind",
            dataIndex: "kind",
            render: (k: string) => <Tag color="blue">{k}</Tag>,
          },
          { title: "Target", dataIndex: "target_ref" },
          { title: "Cluster", dataIndex: "cluster_ref" },
          {
            title: "Direction",
            dataIndex: "direction",
            render: (d: string) => <Tag>{d}</Tag>,
          },
          {
            title: "Enabled",
            dataIndex: "enabled",
            render: (e: boolean) =>
              e ? <Tag color="green">enabled</Tag> : <Tag>disabled</Tag>,
          },
          {
            title: "Actions",
            render: (_: unknown, row: StreamingLink) => (
              <Space>
                <Button size="small" danger onClick={() => deleteLink(row)}>
                  Delete
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
