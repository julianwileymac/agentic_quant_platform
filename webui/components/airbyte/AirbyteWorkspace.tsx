"use client";

import { App, Button, Card, Col, Form, Input, Row, Select, Space, Statistic, Table, Tag, Typography } from "antd";
import { useMemo, useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { useApiQuery } from "@/lib/api/hooks";
import { AirbyteApi, type AirbyteConnection, type AirbyteConnector, type AirbyteRun } from "@/lib/api/airbyte";

type View = "overview" | "connectors" | "builder" | "runs";

interface AirbyteHealthPayload {
  ok: boolean;
  enabled?: boolean;
  base_url?: string;
  airbyte?: { reachable?: boolean; detail?: string; available?: boolean; error?: string };
}

interface Props {
  view: View;
}

export function AirbyteWorkspace({ view }: Props) {
  const { message } = App.useApp();
  const [selectedConnector, setSelectedConnector] = useState("alpha-vantage");
  const [configText, setConfigText] = useState("{}");

  const health = useApiQuery<AirbyteHealthPayload>({
    queryKey: ["airbyte", "health"],
    path: "/airbyte/health",
    staleTime: 30_000,
  });
  const summary = useApiQuery<Record<string, unknown>>({
    queryKey: ["airbyte", "summary"],
    path: "/airbyte/connectors/summary",
    staleTime: 60_000,
  });
  const connectors = useApiQuery<AirbyteConnector[]>({
    queryKey: ["airbyte", "connectors"],
    path: "/airbyte/connectors",
    staleTime: 60_000,
  });
  const connections = useApiQuery<AirbyteConnection[]>({
    queryKey: ["airbyte", "connections"],
    path: "/airbyte/connections",
    staleTime: 30_000,
  });
  const runs = useApiQuery<AirbyteRun[]>({
    queryKey: ["airbyte", "runs"],
    path: "/airbyte/runs",
    staleTime: 15_000,
  });

  const connectorOptions = useMemo(
    () =>
      (connectors.data ?? [])
        .filter((connector) => connector.kind === "source")
        .map((connector) => ({ value: connector.id, label: connector.name })),
    [connectors.data],
  );

  async function queueDiscover() {
    try {
      const task = await AirbyteApi.discover(selectedConnector, parseConfig(configText));
      message.success(`Discovery queued: ${task.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function queueDryRun() {
    try {
      const task = await AirbyteApi.embeddedRead(selectedConnector, parseConfig(configText));
      message.success(`Embedded dry-run queued: ${task.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function queueSync(connectionId: string) {
    try {
      const task = await AirbyteApi.sync(connectionId);
      message.success(`Sync queued: ${task.task_id}`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title={titleFor(view)}
      subtitle="Hybrid Airbyte control plane for production syncs and embedded connector development."
    >
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        {view === "overview" ? (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} md={6}>
                <Card>
                  <Statistic title="Airbyte OK" value={String(health.data?.ok ?? "unknown")} />
                  <Space direction="vertical" size={4} style={{ marginTop: 8 }}>
                    <Tag color={health.data?.enabled ? "blue" : "default"}>
                      {health.data?.enabled ? "enabled" : "disabled"}
                    </Tag>
                    {health.data?.airbyte?.detail ? (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {health.data.airbyte.detail}
                      </Typography.Text>
                    ) : null}
                  </Space>
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card>
                  <Statistic title="Connectors" value={Number(summary.data?.total ?? 0)} />
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card>
                  <Statistic title="Connections" value={connections.data?.length ?? 0} />
                </Card>
              </Col>
              <Col xs={24} md={6}>
                <Card>
                  <Statistic title="Recent runs" value={runs.data?.length ?? 0} />
                </Card>
              </Col>
            </Row>
            <ConnectionsTable rows={connections.data ?? []} loading={connections.isLoading} onSync={queueSync} />
          </>
        ) : null}

        {view === "connectors" ? (
          <ConnectorsTable rows={connectors.data ?? []} loading={connectors.isLoading} />
        ) : null}

        {view === "builder" ? (
          <Card title="Connector development and test runs">
            <Form layout="vertical">
              <Form.Item label="Source connector">
                <Select
                  value={selectedConnector}
                  onChange={setSelectedConnector}
                  options={connectorOptions}
                  style={{ maxWidth: 420 }}
                />
              </Form.Item>
              <Form.Item label="Config JSON">
                <Input.TextArea value={configText} onChange={(event) => setConfigText(event.target.value)} rows={8} />
              </Form.Item>
              <Space>
                <Button onClick={queueDiscover}>Discover streams</Button>
                <Button type="primary" onClick={queueDryRun}>
                  Embedded dry-run
                </Button>
              </Space>
            </Form>
          </Card>
        ) : null}

        {view === "runs" ? <RunsTable rows={runs.data ?? []} loading={runs.isLoading} /> : null}
      </Space>
    </PageContainer>
  );
}

function ConnectorsTable({ rows, loading }: { rows: AirbyteConnector[]; loading: boolean }) {
  return (
    <Table
      rowKey="id"
      loading={loading}
      dataSource={rows}
      columns={[
        { title: "Connector", dataIndex: "name" },
        { title: "Kind", dataIndex: "kind", render: (value: string) => <Tag>{value}</Tag> },
        { title: "Runtime", dataIndex: "runtime", render: (value: string) => <Tag color="blue">{value}</Tag> },
        {
          title: "Streams",
          render: (_, row) => row.streams?.map((stream) => stream.name).join(", ") || "-",
        },
        {
          title: "Tags",
          render: (_, row) => (
            <Space wrap>{row.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
          ),
        },
      ]}
    />
  );
}

function ConnectionsTable({
  rows,
  loading,
  onSync,
}: {
  rows: AirbyteConnection[];
  loading: boolean;
  onSync: (connectionId: string) => void;
}) {
  return (
    <Card title="Configured connections">
      <Table
        rowKey="id"
        loading={loading}
        dataSource={rows}
        columns={[
          { title: "Name", dataIndex: "name" },
          { title: "Source", dataIndex: "source_connector_id" },
          { title: "Destination", dataIndex: "destination_connector_id" },
          { title: "Status", dataIndex: "last_sync_status", render: (value) => value ?? "never" },
          {
            title: "Action",
            render: (_, row) => (
              <Button size="small" onClick={() => onSync(row.id)} disabled={!row.airbyte_connection_id}>
                Queue sync
              </Button>
            ),
          },
        ]}
      />
    </Card>
  );
}

function RunsTable({ rows, loading }: { rows: AirbyteRun[]; loading: boolean }) {
  return (
    <Table
      rowKey="id"
      loading={loading}
      dataSource={rows}
      columns={[
        { title: "Started", dataIndex: "started_at" },
        { title: "Runtime", dataIndex: "runtime" },
        { title: "Status", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
        { title: "Airbyte job", dataIndex: "airbyte_job_id", render: (value) => value ?? "-" },
        {
          title: "Task",
          dataIndex: "task_id",
          render: (value) => value ?? "-",
        },
        { title: "Error", dataIndex: "error", render: (value) => value ?? "-" },
      ]}
    />
  );
}

function parseConfig(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text || "{}") as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Config must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function titleFor(view: View) {
  if (view === "connectors") return "Airbyte connectors";
  if (view === "builder") return "Airbyte builder";
  if (view === "runs") return "Airbyte runs";
  return "Airbyte control";
}
