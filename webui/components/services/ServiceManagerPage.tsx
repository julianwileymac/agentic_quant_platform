"use client";

import { ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import {
  serviceManagerApi,
  type IcebergBootstrapReport,
  type IcebergStatus,
  type ServiceName,
  type TrinoQueryRow,
  type TrinoVerification,
} from "@/lib/api/serviceManager";
import { useApiQuery } from "@/lib/api/hooks";

const SERVICES: ServiceName[] = [
  "trino",
  "polaris",
  "iceberg",
  "superset",
  "airbyte",
  "dagster",
  "neo4j",
];

export function ServiceManagerPage() {
  const { message } = App.useApp();
  const [logs, setLogs] = useState<Record<string, string>>({});
  const [bootstrapReport, setBootstrapReport] = useState<IcebergBootstrapReport | null>(null);
  const [bootstrapBusy, setBootstrapBusy] = useState(false);
  const [verification, setVerification] = useState<TrinoVerification | null>(null);
  const [verifyBusy, setVerifyBusy] = useState(false);

  const health = useApiQuery({
    queryKey: ["service-manager", "health"],
    path: "/service-manager/health",
    staleTime: 10_000,
  });
  const icebergStatus = useApiQuery<IcebergStatus>({
    queryKey: ["service-manager", "iceberg-status"],
    path: "/service-manager/iceberg/status",
    staleTime: 30_000,
  });
  const trinoQueries = useApiQuery<{ queries: TrinoQueryRow[]; count: number }>({
    queryKey: ["service-manager", "trino-queries"],
    path: "/service-manager/trino/queries",
    query: { limit: 25 },
    staleTime: 15_000,
  });

  const payload = health.data as
    | { ok: boolean; services: Record<string, Record<string, unknown>>; config: Record<string, unknown> }
    | undefined;

  async function fetchLogs(name: ServiceName) {
    try {
      const result = await serviceManagerApi.logs(name, 160);
      setLogs((prev) => ({
        ...prev,
        [name]: String(result.stdout || result.stderr || result.error || "No logs returned."),
      }));
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function runAction(name: ServiceName, action: "start" | "stop" | "restart") {
    try {
      await serviceManagerApi.action(name, action);
      message.success(`${action} queued for ${name}`);
      await health.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function runBootstrap() {
    setBootstrapBusy(true);
    try {
      const report = await serviceManagerApi.icebergBootstrap();
      setBootstrapReport(report);
      message.success(report.success ? "Iceberg bootstrap complete" : "Bootstrap finished with errors");
      await Promise.all([health.refetch(), icebergStatus.refetch()]);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setBootstrapBusy(false);
    }
  }

  async function runTrinoVerify() {
    setVerifyBusy(true);
    try {
      const result = await serviceManagerApi.trinoVerify();
      setVerification(result);
      message.success(
        result.query_ok
          ? `Trino query OK (catalogs=${(result.catalogs ?? []).length})`
          : "Trino query verification failed",
      );
      await Promise.all([health.refetch(), trinoQueries.refetch()]);
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setVerifyBusy(false);
    }
  }

  return (
    <PageContainer
      title="Service Manager"
      subtitle="AQP control surface for Trino, Polaris, Iceberg, Superset, Airbyte, Dagster, and Neo4j."
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => health.refetch()}>
          Refresh
        </Button>
      }
    >
      <Card size="small" style={{ marginBottom: 16 }}>
        <Descriptions size="small" column={2} bordered>
          <Descriptions.Item label="Overall">
            <Tag color={payload?.ok ? "success" : "warning"}>
              {payload?.ok ? "healthy" : "attention"}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Control actions">
            <Tag color={payload?.config?.service_control_enabled ? "blue" : "default"}>
              {payload?.config?.service_control_enabled ? "enabled" : "disabled"}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Graph store">
            <code>{String(payload?.config?.graph_store ?? "-")}</code>
          </Descriptions.Item>
          <Descriptions.Item label="Neo4j">
            <code>{String(payload?.config?.neo4j_uri ?? "-")}</code>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} xl={12}>
          <Card
            title={
              <Space>
                <span>Iceberg Bootstrap</span>
                {icebergStatus.data?.catalog_present ? (
                  <Tag color="success">catalog ready</Tag>
                ) : (
                  <Tag color="warning">bootstrap required</Tag>
                )}
              </Space>
            }
            extra={
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={bootstrapBusy}
                onClick={runBootstrap}
              >
                Bootstrap now
              </Button>
            }
          >
            {icebergStatus.data ? (
              <Descriptions size="small" column={2} bordered>
                <Descriptions.Item label="Catalog">
                  <code>{icebergStatus.data.catalog}</code>
                </Descriptions.Item>
                <Descriptions.Item label="Polaris">
                  <Tag color={icebergStatus.data.polaris_reachable ? "success" : "error"}>
                    {icebergStatus.data.polaris_reachable ? "reachable" : "unreachable"}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Catalog present">
                  <Tag color={icebergStatus.data.catalog_present ? "success" : "warning"}>
                    {String(icebergStatus.data.catalog_present)}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Principal present">
                  <Tag color={icebergStatus.data.principal_present ? "success" : "warning"}>
                    {String(icebergStatus.data.principal_present)}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Principal role">
                  <Tag color={icebergStatus.data.principal_role_present ? "success" : "warning"}>
                    {String(icebergStatus.data.principal_role_present)}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Catalog role">
                  <Tag color={icebergStatus.data.catalog_role_present ? "success" : "warning"}>
                    {String(icebergStatus.data.catalog_role_present)}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Credentials persisted" span={2}>
                  <Space>
                    <Tag color={icebergStatus.data.credentials_persisted ? "success" : "default"}>
                      {String(icebergStatus.data.credentials_persisted)}
                    </Tag>
                    {icebergStatus.data.credentials_file ? (
                      <code style={{ fontSize: 11 }}>{icebergStatus.data.credentials_file}</code>
                    ) : null}
                  </Space>
                </Descriptions.Item>
                {icebergStatus.data.error ? (
                  <Descriptions.Item label="Error" span={2}>
                    <Typography.Text type="danger">{icebergStatus.data.error}</Typography.Text>
                  </Descriptions.Item>
                ) : null}
              </Descriptions>
            ) : (
              <Empty description="loading status" />
            )}
            {bootstrapReport ? (
              <Card size="small" title="Last bootstrap report" style={{ marginTop: 12 }}>
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Tag color={bootstrapReport.success ? "success" : "error"}>
                    {bootstrapReport.success ? "success" : "errors"} ({bootstrapReport.duration_seconds}s)
                  </Tag>
                  <Table
                    size="small"
                    rowKey={(row) => row.name}
                    pagination={false}
                    dataSource={bootstrapReport.steps}
                    columns={[
                      { title: "Step", dataIndex: "name" },
                      {
                        title: "Status",
                        dataIndex: "status",
                        render: (value: string) => (
                          <Tag
                            color={
                              value === "ok" || value === "created" || value === "exists"
                                ? "success"
                                : value === "skipped"
                                ? "default"
                                : "error"
                            }
                          >
                            {value}
                          </Tag>
                        ),
                      },
                      { title: "Detail", dataIndex: "detail" },
                    ]}
                  />
                </Space>
              </Card>
            ) : null}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card
            title={
              <Space>
                <span>Trino Verification</span>
                {verification?.query_ok ? (
                  <Tag color="success">query ok</Tag>
                ) : (
                  <Tag color="default">not verified</Tag>
                )}
              </Space>
            }
            extra={
              <Button
                type="primary"
                loading={verifyBusy}
                onClick={runTrinoVerify}
                icon={<ThunderboltOutlined />}
              >
                Run SHOW CATALOGS
              </Button>
            }
          >
            {verification ? (
              <Descriptions size="small" column={2} bordered>
                <Descriptions.Item label="Coordinator">
                  <Tag color={verification.coordinator_ok ? "success" : "error"}>
                    {verification.coordinator_ok ? "ok" : "down"}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Iceberg catalog">
                  <Tag color={verification.iceberg_catalog_ok ? "success" : "warning"}>
                    {verification.iceberg_catalog_ok ? "available" : "missing"}
                  </Tag>
                </Descriptions.Item>
                <Descriptions.Item label="Catalogs" span={2}>
                  <Space wrap>
                    {(verification.catalogs ?? []).map((catalog) => (
                      <Tag key={catalog}>{catalog}</Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="Iceberg schemas" span={2}>
                  <Space wrap>
                    {(verification.iceberg_schemas ?? []).map((schema) => (
                      <Tag key={schema} color="blue">
                        {schema}
                      </Tag>
                    ))}
                  </Space>
                </Descriptions.Item>
                {verification.error ? (
                  <Descriptions.Item label="Error" span={2}>
                    <Typography.Text type="danger">{verification.error}</Typography.Text>
                  </Descriptions.Item>
                ) : null}
              </Descriptions>
            ) : (
              <Empty description="Click 'Run SHOW CATALOGS' to verify" />
            )}
            <Card size="small" style={{ marginTop: 12 }} title={`Recent Trino queries (${trinoQueries.data?.count ?? 0})`}>
              <Table
                size="small"
                rowKey={(row) => `${row.query_id}-${row.created ?? ""}`}
                dataSource={trinoQueries.data?.queries ?? []}
                pagination={{ pageSize: 6 }}
                columns={[
                  { title: "Query", dataIndex: "query_id", width: 140 },
                  {
                    title: "State",
                    dataIndex: "state",
                    width: 90,
                    render: (value: string) => (
                      <Tag color={value === "FINISHED" ? "success" : value === "FAILED" ? "error" : "default"}>
                        {value}
                      </Tag>
                    ),
                  },
                  { title: "User", dataIndex: "user", width: 120 },
                  {
                    title: "Elapsed (s)",
                    dataIndex: "elapsed_seconds",
                    width: 100,
                    render: (value?: number | null) => (value != null ? value.toFixed(2) : "-"),
                  },
                  {
                    title: "Statement",
                    dataIndex: "statement",
                    ellipsis: true,
                  },
                ]}
              />
            </Card>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        {SERVICES.map((name) => {
          const service = payload?.services?.[name] ?? {};
          return (
            <Col xs={24} md={12} xl={8} key={name}>
              <Card
                title={
                  <Space>
                    <span style={{ textTransform: "capitalize" }}>{name}</span>
                    <Tag color={service.ok ? "success" : "error"}>
                      {service.ok ? "up" : "down"}
                    </Tag>
                  </Space>
                }
                extra={<Button size="small" onClick={() => fetchLogs(name)}>Logs</Button>}
              >
                <Space direction="vertical" style={{ width: "100%" }}>
                  {service.error ? (
                    <Typography.Text type="danger" style={{ fontSize: 12 }}>
                      {String(service.error)}
                    </Typography.Text>
                  ) : (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {Object.entries(service)
                        .filter(([key]) =>
                          [
                            "uri",
                            "url",
                            "graphql_url",
                            "coordinator_url",
                            "table_count",
                            "query_ok",
                            "iceberg_catalog_ok",
                            "bootstrap_required",
                          ].includes(key),
                        )
                        .map(([key, value]) => `${key}: ${String(value)}`)
                        .join(" | ") || "No additional status fields."}
                    </Typography.Text>
                  )}
                  <Space wrap>
                    {(["start", "restart", "stop"] as const).map((action) => (
                      <Button size="small" key={action} onClick={() => runAction(name, action)}>
                        {action}
                      </Button>
                    ))}
                  </Space>
                  {logs[name] ? (
                    <pre
                      style={{
                        maxHeight: 180,
                        overflow: "auto",
                        whiteSpace: "pre-wrap",
                        fontSize: 11,
                        background: "var(--ant-color-fill-quaternary)",
                        padding: 8,
                        borderRadius: 6,
                      }}
                    >
                      {logs[name]}
                    </pre>
                  ) : null}
                </Space>
              </Card>
            </Col>
          );
        })}
      </Row>
    </PageContainer>
  );
}
