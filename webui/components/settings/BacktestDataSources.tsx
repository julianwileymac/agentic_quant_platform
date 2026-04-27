"use client";

import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/api/hooks";

const { Text } = Typography;

interface DataSourceRow {
  id: string;
  name: string;
  kind: string;
  config: Record<string, unknown>;
  enabled: boolean;
}

interface PartitionInfo {
  key: string;
  sample_values: string[];
}

interface InspectionReport {
  path: string;
  exists: boolean;
  file_count: number;
  total_bytes: number;
  sample_files: string[];
  partition_keys: PartitionInfo[];
  columns: string[];
  dtypes: Record<string, string>;
  sample_rows: Record<string, unknown>[];
  suggested_glob: string | null;
  suggested_column_map: Record<string, string>;
  hive_partitioning: boolean;
  error: string | null;
}

interface SourceDraft {
  name: string;
  kind: "parquet_root" | "iceberg_table" | "bars_default";
  parquet_root: string;
  iceberg_identifier: string;
  hive_partitioning: boolean;
  glob_pattern: string;
  column_map: {
    timestamp: string;
    vt_symbol: string;
    open: string;
    high: string;
    low: string;
    close: string;
    volume: string;
  };
}

const EMPTY_DRAFT: SourceDraft = {
  name: "",
  kind: "parquet_root",
  parquet_root: "",
  iceberg_identifier: "",
  hive_partitioning: false,
  glob_pattern: "",
  column_map: {
    timestamp: "",
    vt_symbol: "",
    open: "",
    high: "",
    low: "",
    close: "",
    volume: "",
  },
};

function bytesToHuman(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let val = n;
  while (val >= 1024 && i < u.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(1)} ${u[i]}`;
}

export function BacktestDataSources() {
  const { message } = App.useApp();

  const dataSources = useApiQuery<DataSourceRow[]>({
    queryKey: ["backtest", "data-sources"],
    path: "/backtest/data-sources",
    staleTime: 10_000,
    select: (raw) => (Array.isArray(raw) ? (raw as DataSourceRow[]) : []),
  });

  const [draft, setDraft] = useState<SourceDraft>(EMPTY_DRAFT);
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectReport, setInspectReport] = useState<InspectionReport | null>(null);
  const [inspectError, setInspectError] = useState<string | null>(null);

  async function inspect() {
    if (!draft.parquet_root.trim()) {
      message.warning("Enter a parquet root path first");
      return;
    }
    setInspectLoading(true);
    setInspectError(null);
    setInspectReport(null);
    try {
      const res = await apiFetch<InspectionReport>("/backtest/data-sources/inspect", {
        method: "POST",
        body: JSON.stringify({ parquet_root: draft.parquet_root.trim() }),
      });
      setInspectReport(res);
      // Auto-fill suggestions.
      setDraft((prev) => ({
        ...prev,
        hive_partitioning: res.hive_partitioning,
        glob_pattern: res.suggested_glob ?? prev.glob_pattern,
        column_map: {
          ...prev.column_map,
          timestamp:
            res.suggested_column_map?.timestamp ?? prev.column_map.timestamp,
          vt_symbol:
            res.suggested_column_map?.vt_symbol ?? prev.column_map.vt_symbol,
          open: res.suggested_column_map?.open ?? prev.column_map.open,
          high: res.suggested_column_map?.high ?? prev.column_map.high,
          low: res.suggested_column_map?.low ?? prev.column_map.low,
          close: res.suggested_column_map?.close ?? prev.column_map.close,
          volume: res.suggested_column_map?.volume ?? prev.column_map.volume,
        },
      }));
    } catch (err) {
      setInspectError((err as Error).message);
    } finally {
      setInspectLoading(false);
    }
  }

  async function upsertSource() {
    const config: Record<string, unknown> = {};
    if (draft.kind === "parquet_root") {
      config.parquet_root = draft.parquet_root;
      if (draft.hive_partitioning) config.hive_partitioning = true;
      if (draft.glob_pattern) config.glob_pattern = draft.glob_pattern;
      const colMap: Record<string, string> = {};
      for (const [k, v] of Object.entries(draft.column_map)) {
        if (v && v.trim()) colMap[k] = v.trim();
      }
      if (Object.keys(colMap).length) config.column_map = colMap;
    } else if (draft.kind === "iceberg_table") {
      config.iceberg_identifier = draft.iceberg_identifier;
    }
    try {
      await apiFetch("/backtest/data-sources", {
        method: "POST",
        body: JSON.stringify({
          name: draft.name || `source-${Date.now()}`,
          kind: draft.kind,
          config,
          enabled: true,
        }),
      });
      message.success("Backtest data source saved");
      setDraft(EMPTY_DRAFT);
      setInspectReport(null);
      setInspectError(null);
      dataSources.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function removeSource(id: string) {
    try {
      await apiFetch(`/backtest/data-sources/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      message.success("Data source removed");
      dataSources.refetch();
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <Card title="Backtest data sources">
      <Form layout="vertical">
        <Row gutter={16}>
          <Col xs={24} md={8}>
            <Form.Item label="Name">
              <Input
                value={draft.name}
                onChange={(e) => setDraft((p) => ({ ...p, name: e.target.value }))}
                placeholder="CFPB parquet root"
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}>
            <Form.Item label="Kind">
              <Select
                value={draft.kind}
                onChange={(value) =>
                  setDraft((p) => ({ ...p, kind: value as SourceDraft["kind"] }))
                }
                options={[
                  { label: "Parquet root", value: "parquet_root" },
                  { label: "Iceberg table", value: "iceberg_table" },
                  { label: "Default bars", value: "bars_default" },
                ]}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={10}>
            {draft.kind === "parquet_root" ? (
              <Form.Item label="Parquet root path">
                <Input
                  value={draft.parquet_root}
                  onChange={(e) =>
                    setDraft((p) => ({ ...p, parquet_root: e.target.value }))
                  }
                  placeholder="C:/data/parquet/my_dataset"
                />
              </Form.Item>
            ) : draft.kind === "iceberg_table" ? (
              <Form.Item label="Iceberg identifier">
                <Input
                  value={draft.iceberg_identifier}
                  onChange={(e) =>
                    setDraft((p) => ({ ...p, iceberg_identifier: e.target.value }))
                  }
                  placeholder="aqp_ingest.cfpb_public_lar"
                />
              </Form.Item>
            ) : (
              <Form.Item label="Config">
                <Input disabled value="No extra config needed" />
              </Form.Item>
            )}
          </Col>
        </Row>

        {draft.kind === "parquet_root" ? (
          <>
            <Space style={{ marginBottom: 12 }}>
              <Button
                icon={<SearchOutlined />}
                onClick={inspect}
                loading={inspectLoading}
                disabled={!draft.parquet_root.trim()}
              >
                Inspect path
              </Button>
              <Text type="secondary">
                Probe the directory for Hive partitions, columns, and a sample row.
              </Text>
            </Space>
            {inspectError ? (
              <Alert
                type="error"
                showIcon
                message={inspectError}
                style={{ marginBottom: 12 }}
              />
            ) : null}
            {inspectReport ? (
              <Card size="small" style={{ marginBottom: 12 }} title="Inspection report">
                <Descriptions column={3} size="small">
                  <Descriptions.Item label="Files">
                    {inspectReport.file_count}
                  </Descriptions.Item>
                  <Descriptions.Item label="Size">
                    {bytesToHuman(inspectReport.total_bytes)}
                  </Descriptions.Item>
                  <Descriptions.Item label="Hive">
                    <Tag color={inspectReport.hive_partitioning ? "green" : "default"}>
                      {inspectReport.hive_partitioning ? "yes" : "no"}
                    </Tag>
                  </Descriptions.Item>
                  {inspectReport.partition_keys.length ? (
                    <Descriptions.Item label="Partition keys" span={3}>
                      <Space wrap>
                        {inspectReport.partition_keys.map((p) => (
                          <Tag key={p.key} color="blue">
                            {p.key}=({p.sample_values.slice(0, 4).join("|")}
                            {p.sample_values.length > 4 ? ", …" : ""})
                          </Tag>
                        ))}
                      </Space>
                    </Descriptions.Item>
                  ) : null}
                  {inspectReport.columns.length ? (
                    <Descriptions.Item label="Columns" span={3}>
                      <Space wrap size={4}>
                        {inspectReport.columns.slice(0, 30).map((c) => (
                          <Tag key={c}>{c}</Tag>
                        ))}
                        {inspectReport.columns.length > 30 ? (
                          <Text type="secondary">
                            +{inspectReport.columns.length - 30} more
                          </Text>
                        ) : null}
                      </Space>
                    </Descriptions.Item>
                  ) : null}
                  {inspectReport.error ? (
                    <Descriptions.Item label="Note" span={3}>
                      <Text type="warning">{inspectReport.error}</Text>
                    </Descriptions.Item>
                  ) : null}
                </Descriptions>
              </Card>
            ) : null}

            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item label="Hive partitioning">
                  <Switch
                    checked={draft.hive_partitioning}
                    onChange={(v) =>
                      setDraft((p) => ({ ...p, hive_partitioning: v }))
                    }
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={16}>
                <Form.Item
                  label="Glob pattern (optional)"
                  tooltip="Relative to the parquet root, e.g. **/*.parquet"
                >
                  <Input
                    value={draft.glob_pattern}
                    onChange={(e) =>
                      setDraft((p) => ({ ...p, glob_pattern: e.target.value }))
                    }
                    placeholder="**/*.parquet"
                  />
                </Form.Item>
              </Col>
            </Row>
            <Card size="small" title="Column map (optional)">
              <Text type="secondary">
                Map your columns to the canonical bars schema; leave empty for the
                default name.
              </Text>
              <Row gutter={12} style={{ marginTop: 8 }}>
                {(
                  [
                    "timestamp",
                    "vt_symbol",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                  ] as const
                ).map((field) => (
                  <Col xs={24} md={6} key={field}>
                    <Form.Item label={field}>
                      <Input
                        value={draft.column_map[field]}
                        onChange={(e) =>
                          setDraft((p) => ({
                            ...p,
                            column_map: { ...p.column_map, [field]: e.target.value },
                          }))
                        }
                        placeholder={field}
                      />
                    </Form.Item>
                  </Col>
                ))}
              </Row>
            </Card>
          </>
        ) : null}

        <Space style={{ marginTop: 16, marginBottom: 12 }}>
          <Button type="primary" onClick={upsertSource}>
            Save source
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => dataSources.refetch()}>
            Refresh sources
          </Button>
        </Space>
      </Form>

      <Table<DataSourceRow>
        size="small"
        rowKey="id"
        dataSource={dataSources.data ?? []}
        loading={dataSources.isLoading}
        pagination={{ pageSize: 8 }}
        columns={[
          { title: "Name", dataIndex: "name", key: "name" },
          {
            title: "Kind",
            dataIndex: "kind",
            key: "kind",
            render: (v) => <Tag>{String(v)}</Tag>,
          },
          {
            title: "Config",
            dataIndex: "config",
            key: "config",
            render: (cfg: Record<string, unknown> | undefined) => (
              <code style={{ fontSize: 11 }}>
                {JSON.stringify(cfg ?? {})}
              </code>
            ),
          },
          {
            title: "Actions",
            key: "actions",
            render: (_v, row) =>
              row.id === "default-bars" ? (
                <Text type="secondary">system</Text>
              ) : (
                <Button danger size="small" onClick={() => removeSource(row.id)}>
                  Delete
                </Button>
              ),
          },
        ]}
      />

    </Card>
  );
}
